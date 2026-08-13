from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.payments.models import PaymentTransaction
from yitu.platform.audit import AuditService
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.platform.outbox import OutboxService
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.schemas import CreateShipmentCommand
from yitu.shipments.state_machine import transition
from yitu.sla.models import SLAInstance
from yitu.stations.service import match_station
from yitu.tracking.models import TrackingEvent
from yitu.tracking.schemas import TrackingEventView
from yitu.tracking.service import append_tracking_event, list_tracking_events


class ShipmentView(BaseModel):
    """创建运单后对调用方返回的稳定视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    shipment_no: str
    owner_id: UUID
    status: ShipmentStatus


class ShipmentListResponse(BaseModel):
    """运单列表响应，供前端列表页按当前身份安全分页读取。"""

    items: list[ShipmentView]
    total: int
    limit: int
    offset: int


class ShipmentReadView(BaseModel):
    """供只读工具使用的最小运单聚合，不包含地址和联系方式。"""

    shipment: ShipmentView
    tracking: list[TrackingEventView]
    paid_total_cents: int
    eta_at: datetime | None
    promised_delivery_at: datetime | None


class ShipmentApplicationService:
    """负责创建运单聚合并保证请求幂等。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        actor: CurrentUser,
        *,
        shipment_status: ShipmentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ShipmentListResponse:
        """按身份范围返回运单列表：客户仅本人，运营管理员可看全部。"""
        if actor.role is Role.CUSTOMER:
            base_query = select(Shipment).where(Shipment.owner_id == actor.id)
            count_query = select(func.count()).select_from(Shipment).where(
                Shipment.owner_id == actor.id
            )
        elif actor.role is Role.OPERATIONS_ADMIN:
            base_query = select(Shipment)
            count_query = select(func.count()).select_from(Shipment)
        else:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        if shipment_status is not None:
            base_query = base_query.where(Shipment.status == shipment_status)
            count_query = count_query.where(Shipment.status == shipment_status)
        rows = (
            await self._session.scalars(
                base_query.order_by(Shipment.shipment_no.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        total = await self._session.scalar(count_query)
        return ShipmentListResponse(
            items=[ShipmentView.model_validate(shipment) for shipment in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def create(
        self, command: CreateShipmentCommand, actor: CurrentUser, idempotency_key: str
    ) -> ShipmentView:
        # 当前网点自动匹配能力尚未覆盖客户自寄、自提场景，新运单只开放门到门服务。
        if command.draft.pickup_method is not PickupMethod.DOOR_PICKUP:
            raise AppError(
                "STATION_DROPOFF_DISABLED",
                "暂不支持网点寄件，请选择上门取件",
                422,
            )
        if command.draft.delivery_method is not DeliveryMethod.HOME_DELIVERY:
            raise AppError(
                "STATION_PICKUP_DISABLED",
                "暂不支持网点自提，请选择送货上门",
                422,
            )
        payload = command.model_dump(mode="json")
        request_hash = canonical_json_sha256(payload)
        scope = f"shipment:create:{actor.id}"

        async def operation() -> IdempotencyResponse:
            draft = command.draft
            sender = (
                await self._session.get(Address, draft.sender_address_id)
                if draft.sender_address_id is not None
                else None
            )
            receiver = (
                await self._session.get(Address, draft.receiver_address_id)
                if draft.receiver_address_id is not None
                else None
            )
            if draft.sender_address_id is not None and sender is None:
                raise ValueError("寄件地址不存在")
            if draft.receiver_address_id is not None and receiver is None:
                raise ValueError("收件地址不存在")
            if sender is not None:
                require_resource_owner(sender.owner_id, actor)
            if receiver is not None:
                require_resource_owner(receiver.owner_id, actor)
            origin_station_id = draft.origin_station_id
            destination_station_id = draft.destination_station_id
            if draft.pickup_method.value == "DOOR_PICKUP" and sender is not None:
                origin_station_id = (await match_station(self._session, sender.district_code, "HOME_PICKUP")).id
            if draft.delivery_method.value == "HOME_DELIVERY" and receiver is not None:
                destination_station_id = (await match_station(self._session, receiver.district_code, "HOME_DELIVERY")).id
            shipment = Shipment(
                shipment_no=f"YT{uuid4().hex[:16].upper()}",
                owner_id=actor.id,
                sender_address_id=sender.id if sender is not None else None,
                receiver_address_id=receiver.id if receiver is not None else None,
                origin_station_id=origin_station_id,
                destination_station_id=destination_station_id,
                pickup_method=draft.pickup_method,
                delivery_method=draft.delivery_method,
                status=ShipmentStatus.PENDING_PAYMENT,
            )
            self._session.add(shipment)
            await self._session.flush()
            view = ShipmentView.model_validate(shipment)
            await OutboxService(self._session).append(
                event_type="shipment.created",
                business_id=f"shipment:{shipment.id}",
                payload={"shipment_id": str(shipment.id), "shipment_no": shipment.shipment_no},
                idempotency_key=f"shipment:{shipment.id}:created",
            )
            return IdempotencyResponse(status_code=201, body=view.model_dump(mode="json"))

        response = await IdempotencyService(self._session).execute(
            scope, idempotency_key, request_hash, operation
        )
        return ShipmentView.model_validate(response.body)

    async def get_read_view(
        self,
        actor: CurrentUser,
        *,
        shipment_no: str | None = None,
    ) -> ShipmentReadView | None:
        """按当前客户范围聚合运单、轨迹、净支付金额和最新 ETA。"""
        if actor.role is not Role.CUSTOMER:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        statement = select(Shipment).where(Shipment.owner_id == actor.id)
        if shipment_no is not None:
            statement = statement.where(Shipment.shipment_no == shipment_no)
        shipment = await self._session.scalar(
            statement.order_by(Shipment.shipment_no.desc()).limit(1)
        )
        if shipment is None:
            return None

        payment_amount = await self._session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PaymentTransaction.transaction_type == "REFUND",
                                -PaymentTransaction.amount_cents,
                            ),
                            else_=PaymentTransaction.amount_cents,
                        )
                    ),
                    0,
                )
            ).where(
                PaymentTransaction.shipment_id == shipment.id,
                PaymentTransaction.status == "SUCCEEDED",
            )
        )
        latest_sla = await self._session.scalar(
            select(SLAInstance)
            .where(SLAInstance.shipment_id == shipment.id)
            .order_by(SLAInstance.started_at.desc().nullslast(), SLAInstance.id.desc())
            .limit(1)
        )
        tracking = await list_tracking_events(self._session, shipment.id)
        return ShipmentReadView(
            shipment=ShipmentView.model_validate(shipment),
            tracking=[TrackingEventView.model_validate(event) for event in tracking],
            paid_total_cents=int(payment_amount or 0),
            eta_at=latest_sla.eta_at if latest_sla is not None else None,
            promised_delivery_at=(
                latest_sla.promised_delivery_at if latest_sla is not None else None
            ),
        )


class ShipmentTransitionService:
    """在同一事务中写入状态、轨迹和审计事实。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transition(
        self,
        shipment: Shipment,
        target: ShipmentStatus,
        actor: CurrentUser,
        action: str,
        request_id: str,
    ) -> TrackingEvent:
        """执行受状态机约束的动作，并将结果追加为客户轨迹。"""
        event_key = f"shipment:{shipment.id}:{action}:{request_id}"
        existing = await self._session.scalar(
            select(TrackingEvent).where(
                TrackingEvent.shipment_id == shipment.id,
                TrackingEvent.idempotency_key == event_key,
            )
        )
        if existing is not None:
            return existing
        previous = ShipmentStatus(shipment.status)
        shipment.status = transition(previous, target)
        event = await append_tracking_event(
            self._session,
            shipment.id,
            event_type=action,
            message=f"运单状态已更新为 {target.value}",
            idempotency_key=event_key,
        )
        await AuditService(self._session).record(
            actor=str(actor.id),
            action=f"shipment.{action}",
            resource=f"shipment:{shipment.id}",
            before_summary={"status": previous.value},
            after_summary={"status": target.value},
            reason=None,
            request_id=request_id,
        )
        return event
