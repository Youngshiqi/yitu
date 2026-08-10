from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.platform.audit import AuditService
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.platform.outbox import OutboxService
from yitu.shipments.enums import ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.schemas import CreateShipmentCommand
from yitu.shipments.state_machine import transition
from yitu.tracking.models import TrackingEvent
from yitu.tracking.service import append_tracking_event


class ShipmentView(BaseModel):
    """创建运单后对调用方返回的稳定视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    shipment_no: str
    owner_id: UUID
    status: ShipmentStatus


class ShipmentApplicationService:
    """负责创建运单聚合并保证请求幂等。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, command: CreateShipmentCommand, actor: CurrentUser, idempotency_key: str
    ) -> ShipmentView:
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
            shipment = Shipment(
                shipment_no=f"YT{uuid4().hex[:16].upper()}",
                owner_id=actor.id,
                sender_address_id=sender.id if sender is not None else None,
                receiver_address_id=receiver.id if receiver is not None else None,
                origin_station_id=draft.origin_station_id,
                destination_station_id=draft.destination_station_id,
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
