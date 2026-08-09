import asyncio
from uuid import UUID, uuid4

from sqlalchemy import text

from yitu.platform.database import SessionFactory
from yitu.platform.outbox import OutboxService, consume_once


async def test_duplicate_delivery_changes_observable_state_once() -> None:
    async with SessionFactory() as session, session.begin():
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:S001",
            payload={"shipment_id": "S001"},
            idempotency_key=f"notification:{uuid4()}",
        )
        await session.execute(
            text("UPDATE outbox_events SET status = 'published' WHERE id = :event_id"),
            {"event_id": event_id},
        )

    barrier = asyncio.Barrier(2)
    handled: list[UUID] = []

    async def handler(payload: dict[str, object], idempotency_key: str) -> None:
        assert payload == {"shipment_id": "S001"}
        assert idempotency_key.startswith("notification:")
        handled.append(event_id)
        await asyncio.sleep(0.05)

    async def invoke() -> bool:
        async with SessionFactory() as session, session.begin():
            await session.execute(text("SELECT 1"))
            await barrier.wait()
            return await consume_once(session, event_id, handler)

    results = await asyncio.gather(invoke(), invoke())

    async with SessionFactory() as session:
        status = await session.scalar(
            text("SELECT status FROM outbox_events WHERE id = :event_id"),
            {"event_id": event_id},
        )

    assert sorted(results) == [False, True]
    assert handled == [event_id]
    assert status == "completed"
