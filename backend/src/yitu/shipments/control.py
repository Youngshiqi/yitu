from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment


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
