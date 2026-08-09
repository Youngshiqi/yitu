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


async def test_five_failures_create_database_dead_letter() -> None:
    idempotency_key = f"notification:{uuid4()}"
    async with SessionFactory() as session, session.begin():
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:S002",
            payload={"shipment_id": "S002"},
            idempotency_key=idempotency_key,
        )

    async def failing_handler(
        payload: dict[str, object], handler_key: str
    ) -> None:
        assert payload == {"shipment_id": "S002"}
        assert handler_key == idempotency_key
        raise RuntimeError("模拟通知服务不可用")

    for _ in range(5):
        async with SessionFactory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE outbox_events SET status = 'published' "
                    "WHERE id = :event_id AND status <> 'dead'"
                ),
                {"event_id": event_id},
            )
            await consume_once(session, event_id, failing_handler)

    async with SessionFactory() as session:
        event = (
            await session.execute(
                text(
                    "SELECT status, attempts, last_error FROM outbox_events "
                    "WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )
        ).mappings().one()
        dead_letter = (
            await session.execute(
                text(
                    "SELECT idempotency_key, attempts, last_error "
                    "FROM dead_letters WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )
        ).mappings().one()

    assert dict(event) == {
        "status": "dead",
        "attempts": 5,
        "last_error": "模拟通知服务不可用",
    }
    assert dict(dead_letter) == {
        "idempotency_key": idempotency_key,
        "attempts": 5,
        "last_error": "模拟通知服务不可用",
    }
