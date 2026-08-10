from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.shipments.enums import ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment
from yitu.shipments.transport_models import TransportLeg, TransportLegStatus


class ShipmentControlService:
    """统一管理运单履约锁和异常冻结事实。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_shipment(self, shipment_id: UUID) -> Shipment:
        shipment = await self._session.scalar(
            select(Shipment).where(Shipment.id == shipment_id).with_for_update()
        )
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        return shipment

    async def lock_and_assert_fulfillment_allowed(self, shipment_id: UUID) -> Shipment:
        shipment = await self.lock_shipment(shipment_id)
        active_hold = await self._session.scalar(
            select(ShipmentHold.id)
            .where(
                ShipmentHold.shipment_id == shipment_id,
                ShipmentHold.active.is_(True),
            )
            .limit(1)
        )
        if active_hold is not None:
            raise AppError(
                "SHIPMENT_FULFILLMENT_BLOCKED",
                "运单存在处理中异常，暂不能推进履约",
                409,
            )
        return shipment

    async def place_exception_hold(
        self,
        *,
        shipment_id: UUID,
        source_type: str,
        source_id: UUID,
        reason: str,
        actor: CurrentUser,
        idempotency_key: str,
    ) -> ShipmentHold:
        shipment = await self.lock_shipment(shipment_id)
        existing = await self._session.scalar(
            select(ShipmentHold).where(
                ShipmentHold.source_type == source_type,
                ShipmentHold.source_id == source_id,
            )
        )
        if existing is not None:
            return existing
        hold = ShipmentHold(
            shipment_id=shipment.id,
            source_type=source_type,
            source_id=source_id,
            frozen_status=shipment.status,
            reason=reason,
            active=True,
            placed_by=actor.id,
            placed_at=Clock.now(),
            place_idempotency_key=idempotency_key,
        )
        self._session.add(hold)
        await self._session.flush()
        return hold

    async def release_exception_holds(
        self,
        *,
        shipment_id: UUID,
        source_type: str,
        source_ids: Sequence[UUID],
        actor: CurrentUser,
        idempotency_key: str,
    ) -> list[ShipmentHold]:
        await self.lock_shipment(shipment_id)
        if not source_ids:
            return []
        holds = list(
            await self._session.scalars(
                select(ShipmentHold)
                .where(
                    ShipmentHold.shipment_id == shipment_id,
                    ShipmentHold.source_type == source_type,
                    ShipmentHold.source_id.in_(source_ids),
                    ShipmentHold.active.is_(True),
                )
                .with_for_update()
            )
        )
        now = Clock.now()
        for hold in holds:
            hold.active = False
            hold.released_by = actor.id
            hold.released_at = now
            hold.release_idempotency_key = idempotency_key
        await self._session.flush()
        return holds

    async def assert_resume_preconditions(
        self,
        shipment: Shipment,
        target_status: ShipmentStatus,
    ) -> None:
        """校验恢复目标阶段仍有必要前置事实；不自动修复履约状态。"""
        if ShipmentStatus(shipment.status) is not target_status:
            raise AppError("RESUME_TARGET_MISMATCH", "运单当前阶段与恢复目标不一致", 409)
        if target_status is ShipmentStatus.PICKUP_ASSIGNED:
            await self._require_active_task(shipment.id, CourierTaskType.PICKUP)
        elif target_status in {ShipmentStatus.DELIVERY_ASSIGNED, ShipmentStatus.OUT_FOR_DELIVERY}:
            await self._require_active_task(shipment.id, CourierTaskType.DELIVERY)
        elif target_status is ShipmentStatus.IN_LINEHAUL:
            active_leg = await self._session.scalar(
                select(TransportLeg.id)
                .where(
                    TransportLeg.shipment_id == shipment.id,
                    TransportLeg.status == TransportLegStatus.IN_TRANSIT,
                )
                .limit(1)
            )
            if active_leg is None:
                raise AppError("RESUME_PRECONDITION_FAILED", "缺少进行中的干线运输段", 409)

    async def _require_active_task(
        self,
        shipment_id: UUID,
        task_type: CourierTaskType,
    ) -> None:
        task_id = await self._session.scalar(
            select(CourierTask.id)
            .where(
                CourierTask.shipment_id == shipment_id,
                CourierTask.task_type == task_type,
                CourierTask.status.in_([CourierTaskStatus.AVAILABLE, CourierTaskStatus.ACCEPTED]),
            )
            .limit(1)
        )
        if task_id is None:
            raise AppError("RESUME_PRECONDITION_FAILED", "缺少有效履约任务", 409)
