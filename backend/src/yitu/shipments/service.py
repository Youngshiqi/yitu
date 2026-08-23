from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from yitu.addresses.models import Address
from yitu.addresses.service import address_response
from yitu.dispatch.models import CourierTask
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.payments.models import PaymentTransaction
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.platform.outbox import OutboxService
from yitu.pricing.models import QuoteSnapshot
from yitu.pricing.schemas import ReweighRequest
from yitu.pricing.service import PricingService
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment, ShipmentPackage
from yitu.shipments.schemas import CreateShipmentCommand, ReweighCommand
from yitu.shipments.state_machine import transition
from yitu.sla.models import SLAInstance
from yitu.sla.service import SLAService
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
    delivery_method: DeliveryMethod
    quote_id: UUID | None = None
    package_id: UUID | None = None
    created_at: datetime


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
    paid_at: datetime | None = None
    eta_at: datetime | None
    promised_delivery_at: datetime | None
    sender_address: dict[str, object] | None = None
    receiver_address: dict[str, object] | None = None
    package: dict[str, object] | None = None
    quote: dict[str, object] | None = None


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
        elif actor.role is Role.STATION_OPERATOR:
            if actor.station_id is None:
                raise AppError("FORBIDDEN_STATION_SCOPE", "station operator missing station scope", 403)
            station_scope = (
                (Shipment.origin_station_id == actor.station_id)
                | (Shipment.destination_station_id == actor.station_id)
            )
            base_query = select(Shipment).where(station_scope)
            count_query = select(func.count()).select_from(Shipment).where(
                station_scope
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
                base_query.order_by(Shipment.created_at.desc(), Shipment.shipment_no.desc())
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
            if draft.quote_id is None:
                raise AppError("QUOTE_REQUIRED", "创建运单前必须先生成报价", 409)
            if any(
                value is None
                for value in (
                    draft.package_category,
                    draft.package_description,
                    draft.estimated_weight_grams,
                    draft.estimated_length_cm,
                    draft.estimated_width_cm,
                    draft.estimated_height_cm,
                )
            ):
                raise AppError("PACKAGE_REQUIRED", "创建运单前必须填写包裹申报信息", 409)
            quote = await self._session.get(QuoteSnapshot, draft.quote_id)
            if quote is None or quote.owner_id != actor.id:
                raise AppError("QUOTE_NOT_FOUND", "报价不存在或不属于当前客户", 409)
            quote_input = quote.input_snapshot
            if quote_input.get("actual_weight_grams") != draft.estimated_weight_grams or quote_input.get("length_cm") != draft.estimated_length_cm or quote_input.get("width_cm") != draft.estimated_width_cm or quote_input.get("height_cm") != draft.estimated_height_cm:
                raise AppError("QUOTE_INPUT_MISMATCH", "报价与包裹申报信息不一致，请重新报价", 409)
            origin_station_id = draft.origin_station_id
            destination_station_id = draft.destination_station_id
            if draft.pickup_method.value == "DOOR_PICKUP" and sender is not None:
                origin_station_id = (await match_station(self._session, sender.district_code, "HOME_PICKUP")).id
            if draft.delivery_method.value == "HOME_DELIVERY" and receiver is not None:
                destination_station_id = (await match_station(self._session, receiver.district_code, "HOME_DELIVERY")).id
            package = ShipmentPackage(
                category=draft.package_category,
                description=draft.package_description,
                estimated_weight_grams=draft.estimated_weight_grams,
                estimated_length_cm=draft.estimated_length_cm,
                estimated_width_cm=draft.estimated_width_cm,
                estimated_height_cm=draft.estimated_height_cm,
                special_instructions=draft.special_instructions,
            )
            self._session.add(package)
            await self._session.flush()
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
                quote_id=quote.id,
                package_id=package.id,
                created_at=Clock.now(),
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
        paid_at = await self._session.scalar(
            select(PaymentTransaction.created_at)
            .where(
                PaymentTransaction.shipment_id == shipment.id,
                PaymentTransaction.transaction_type == "PAYMENT",
                PaymentTransaction.status == "SUCCEEDED",
            )
            .order_by(PaymentTransaction.created_at.asc())
            .limit(1)
        )
        sender = await self._session.scalar(
            select(Address).where(Address.id == shipment.sender_address_id).options(
                selectinload(Address.province_region), selectinload(Address.city_region), selectinload(Address.district_region)
            )
        ) if shipment.sender_address_id is not None else None
        receiver = await self._session.scalar(
            select(Address).where(Address.id == shipment.receiver_address_id).options(
                selectinload(Address.province_region), selectinload(Address.city_region), selectinload(Address.district_region)
            )
        ) if shipment.receiver_address_id is not None else None
        package = await self._session.get(ShipmentPackage, shipment.package_id) if shipment.package_id is not None else None
        quote = await self._session.get(QuoteSnapshot, shipment.quote_id) if shipment.quote_id is not None else None
        tracking = await list_tracking_events(self._session, shipment.id)
        return ShipmentReadView(
            shipment=ShipmentView.model_validate(shipment),
            tracking=[TrackingEventView.model_validate(event) for event in tracking],
            paid_total_cents=int(payment_amount or 0),
            paid_at=paid_at,
            eta_at=latest_sla.eta_at if latest_sla is not None else None,
            promised_delivery_at=(
                latest_sla.promised_delivery_at if latest_sla is not None else None
            ),
            sender_address=address_response(sender) if sender is not None else None,
            receiver_address=address_response(receiver) if receiver is not None else None,
            package={
                "category": package.category,
                "description": package.description,
                "estimated_weight_grams": package.estimated_weight_grams,
                "estimated_length_cm": package.estimated_length_cm,
                "estimated_width_cm": package.estimated_width_cm,
                "estimated_height_cm": package.estimated_height_cm,
                "declared_value_cents": package.declared_value_cents,
                "special_instructions": package.special_instructions,
                "actual_weight_grams": package.actual_weight_grams,
                "actual_length_cm": package.actual_length_cm,
                "actual_width_cm": package.actual_width_cm,
                "actual_height_cm": package.actual_height_cm,
            } if package is not None else None,
            quote={
                "id": quote.id,
                "rule_version": quote.rule_version,
                "fee_items": quote.fee_items,
                "total_cents": quote.total_cents,
                "billable_weight_grams": quote.billable_weight_grams,
            } if quote is not None else None,
        )

    async def get_detail(self, shipment_id: UUID, actor: CurrentUser) -> ShipmentReadView | None:
        """杩斿洖瀹㈡埛璇︽儏椤甸渶瑕佺殑杩愬崟銆佸湴鍧€銆佸寘瑁广€佹姤浠峰拰杞ㄨ抗鑱氬悎銆?"""
        # 瀹㈡埛鍙兘鏌ョ湅鑷繁鐨勮繍鍗曪紱缃戠偣鍛樼湅鏈綉鐐癸紱蹇€掑憳鍙兘鐪嬭嚜宸插凡鎺ュ崟鐨勫彇浠/娲鹃€佷换鍔★紱杩愯惀鍙湅鍏ㄩ儴銆?
        if actor.role is Role.CUSTOMER:
            statement = select(Shipment).where(
                Shipment.id == shipment_id,
                Shipment.owner_id == actor.id,
            )
        elif actor.role is Role.STATION_OPERATOR:
            if actor.station_id is None:
                raise AppError("FORBIDDEN_STATION_SCOPE", "缃戠偣鍛樼己灏戞墍灞炵綉鐐?", 403)
            statement = select(Shipment).where(
                Shipment.id == shipment_id,
                (Shipment.origin_station_id == actor.station_id)
                | (Shipment.destination_station_id == actor.station_id),
            )
        elif actor.role is Role.COURIER:
            # 快递员可查看本网点任务（含待接单共享任务）以及本人已接单任务，
            # 地址是完成取/派任务的前提，范围与任务列表一致（station_id 匹配）。
            if actor.station_id is None:
                raise AppError("FORBIDDEN_STATION_SCOPE", "快递员缺少所属网点", 403)
            statement = select(Shipment).where(
                Shipment.id == shipment_id,
                Shipment.id.in_(
                    select(CourierTask.shipment_id).where(
                        CourierTask.shipment_id == shipment_id,
                        (CourierTask.assignee_id == actor.id)
                        | (CourierTask.station_id == actor.station_id),
                    )
                ),
            )
        elif actor.role is Role.OPERATIONS_ADMIN:
            statement = select(Shipment).where(Shipment.id == shipment_id)
        else:
            raise AppError("FORBIDDEN_ROLE", "瑙掕壊鏉冮檺涓嶈冻", 403)
        shipment = await self._session.scalar(statement)
        if shipment is None:
            return None
        return await self._build_detail(shipment)

    async def _build_detail(self, shipment: Shipment) -> ShipmentReadView:
        payment_amount = await self._session.scalar(
            select(func.coalesce(func.sum(case((PaymentTransaction.transaction_type == "REFUND", -PaymentTransaction.amount_cents), else_=PaymentTransaction.amount_cents)), 0)).where(
                PaymentTransaction.shipment_id == shipment.id, PaymentTransaction.status == "SUCCEEDED"
            )
        )
        paid_at = await self._session.scalar(
            select(PaymentTransaction.created_at)
            .where(
                PaymentTransaction.shipment_id == shipment.id,
                PaymentTransaction.transaction_type == "PAYMENT",
                PaymentTransaction.status == "SUCCEEDED",
            )
            .order_by(PaymentTransaction.created_at.asc())
            .limit(1)
        )
        sender = await self._load_address(shipment.sender_address_id)
        receiver = await self._load_address(shipment.receiver_address_id)
        package = await self._session.get(ShipmentPackage, shipment.package_id) if shipment.package_id else None
        quote = await self._session.get(QuoteSnapshot, shipment.quote_id) if shipment.quote_id else None
        tracking = await list_tracking_events(self._session, shipment.id)
        return ShipmentReadView(
            shipment=ShipmentView.model_validate(shipment), tracking=[TrackingEventView.model_validate(item) for item in tracking],
            paid_total_cents=int(payment_amount or 0), paid_at=paid_at, eta_at=None, promised_delivery_at=None,
            sender_address=address_response(sender) if sender else None,
            receiver_address=address_response(receiver) if receiver else None,
            package=self._package_view(package), quote=self._quote_view(quote),
        )

    async def _load_address(self, address_id: UUID | None) -> Address | None:
        if address_id is None:
            return None
        return cast(Address | None, await self._session.scalar(select(Address).where(Address.id == address_id).options(selectinload(Address.province_region), selectinload(Address.city_region), selectinload(Address.district_region))))

    @staticmethod
    def _package_view(package: ShipmentPackage | None) -> dict[str, object] | None:
        if package is None:
            return None
        return {"category": package.category, "description": package.description, "estimated_weight_grams": package.estimated_weight_grams, "estimated_length_cm": package.estimated_length_cm, "estimated_width_cm": package.estimated_width_cm, "estimated_height_cm": package.estimated_height_cm, "declared_value_cents": package.declared_value_cents, "special_instructions": package.special_instructions, "actual_weight_grams": package.actual_weight_grams, "actual_length_cm": package.actual_length_cm, "actual_width_cm": package.actual_width_cm, "actual_height_cm": package.actual_height_cm}

    @staticmethod
    def _quote_view(quote: QuoteSnapshot | None) -> dict[str, object] | None:
        if quote is None:
            return None
        return {"id": quote.id, "rule_version": quote.rule_version, "fee_items": quote.fee_items, "total_cents": quote.total_cents, "billable_weight_grams": quote.billable_weight_grams}

    async def reweigh(self, shipment_id: UUID, command: ReweighCommand, actor: CurrentUser) -> QuoteSnapshot:
        """锁定运单并保存复重事实，返回基于实际尺寸的新报价。"""
        if actor.role is not Role.COURIER:
            raise AppError("FORBIDDEN_ROLE", "只有揽收快递员可以复重", 403)
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None or shipment.package_id is None or shipment.quote_id is None:
            raise AppError("SHIPMENT_PACKAGE_REQUIRED", "运单缺少包裹或报价", 409)
        package = await self._session.get(ShipmentPackage, shipment.package_id)
        if package is None:
            raise AppError("SHIPMENT_PACKAGE_REQUIRED", "运单包裹不存在", 409)
        package.actual_weight_grams = command.actual_weight_grams
        package.actual_length_cm = command.actual_length_cm
        package.actual_width_cm = command.actual_width_cm
        package.actual_height_cm = command.actual_height_cm
        package.reweighed_by = actor.id
        package.reweighed_at = Clock.now()
        quote = await PricingService(self._session).reweigh(
            shipment.quote_id,
            ReweighRequest(
                actual_weight_grams=command.actual_weight_grams,
                length_cm=command.actual_length_cm,
                width_cm=command.actual_width_cm,
                height_cm=command.actual_height_cm,
            ),
            actor,
        )
        paid_total = await self._session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (PaymentTransaction.transaction_type == "REFUND", -PaymentTransaction.amount_cents),
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
        difference = quote.total_cents - int(paid_total or 0)
        if difference > 0:
            shipment.status = ShipmentStatus.AWAITING_SUPPLEMENT
            await OutboxService(self._session).append(
                event_type="notification.requested", business_id=f"shipment:{shipment.id}",
                payload={"recipient_id": str(shipment.owner_id), "template_code": "SUPPLEMENT_REQUIRED", "template_data": {"shipment_no": shipment.shipment_no, "shipment_id": str(shipment.id), "quote_id": str(quote.id), "amount_cents": difference, "amount_yuan": f"{difference / 100:.2f}"}},
                idempotency_key=f"notification:{shipment.id}:supplement:{quote.id}",
            )
        elif difference < 0:
            self._session.add(PaymentTransaction(owner_id=shipment.owner_id, quote_id=quote.id, shipment_id=shipment.id, transaction_type="REFUND", status="SUCCEEDED", amount_cents=-difference, idempotency_key=f"mock-reweigh-refund:{shipment.id}:{quote.id}", request_hash=canonical_json_sha256({"shipment_id": str(shipment.id), "quote_id": str(quote.id), "amount_cents": -difference}), created_at=Clock.now()))
        elif ShipmentStatus(shipment.status) is ShipmentStatus.AWAITING_SUPPLEMENT:
            shipment.status = ShipmentStatus.PICKUP_ASSIGNED
        shipment.quote_id = quote.id
        await self._session.flush()
        return quote


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
        await SLAService(self._session).sync_shipment_transition(
            shipment, previous, target
        )
        event = await append_tracking_event(
            self._session,
            shipment.id,
            event_type=action,
            message=f"运单状态已更新为 {target.value}",
            idempotency_key=event_key,
        )
        await OutboxService(self._session).append(
            event_type="notification.requested",
            business_id=f"shipment:{shipment.id}",
            payload={
                "recipient_id": str(shipment.owner_id),
                "template_code": "SHIPMENT_STATUS_UPDATED",
                "template_data": {"shipment_no": shipment.shipment_no, "status": target.value},
            },
            idempotency_key=f"notification:{shipment.id}:status:{action}:{request_id}",
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

