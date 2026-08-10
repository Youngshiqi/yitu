from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.clock import Clock
from yitu.tracking.models import TrackingEvent


async def append_tracking_event(session: AsyncSession, shipment_id: UUID, event_type: str, message: str, idempotency_key: str, *, visible_to_customer: bool = True) -> TrackingEvent:
    """追加轨迹；相同幂等键重放时返回已有事件。"""
    existing = await session.scalar(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment_id, TrackingEvent.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    latest_sequence = await session.scalar(select(func.max(TrackingEvent.sequence_no)).where(TrackingEvent.shipment_id == shipment_id))
    event = TrackingEvent(shipment_id=shipment_id, sequence_no=(latest_sequence or 0) + 1, event_type=event_type, message=message, visible_to_customer=visible_to_customer, idempotency_key=idempotency_key, occurred_at=Clock().now())
    session.add(event)
    await session.flush()
    return event


async def list_tracking_events(session: AsyncSession, shipment_id: UUID) -> list[TrackingEvent]:
    """按事件序号返回客户可见轨迹。"""
    events = await session.scalars(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment_id, TrackingEvent.visible_to_customer.is_(True)).order_by(TrackingEvent.sequence_no))
    return list(events)
