import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError
from yitu.platform.outbox import DeadLetterService, OutboxService, consume_once


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


async def test_dead_letter_replay_preserves_original_idempotency_key() -> None:
    idempotency_key = f"notification:{uuid4()}"
    dead_letter_id = uuid4()
    async with SessionFactory() as session, session.begin():
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:S003",
            payload={"shipment_id": "S003"},
            idempotency_key=idempotency_key,
        )
        await session.execute(
            text(
                "UPDATE outbox_events SET status = 'dead', attempts = 5, "
                "last_error = '模拟失败' WHERE id = :event_id"
            ),
            {"event_id": event_id},
        )
        await session.execute(
            text(
                "INSERT INTO dead_letters ("
                "id, event_id, event_type, business_id, payload, idempotency_key, "
                "attempts, last_error, failed_at, suggested_action"
                ") VALUES ("
                ":id, :event_id, 'notification.requested', 'shipment:S003', "
                "CAST('{\"shipment_id\":\"S003\"}' AS JSONB), :idempotency_key, "
                "5, '模拟失败', CURRENT_TIMESTAMP, '修复后重放'"
                ")"
            ),
            {
                "id": dead_letter_id,
                "event_id": event_id,
                "idempotency_key": idempotency_key,
            },
        )

    async with SessionFactory() as session, session.begin():
        replayed_event_id = await DeadLetterService(session).replay(dead_letter_id)

    async with SessionFactory() as session:
        event = (
            await session.execute(
                text(
                    "SELECT status, attempts, idempotency_key, last_error "
                    "FROM outbox_events WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )
        ).mappings().one()
        replayed_at = await session.scalar(
            text("SELECT replayed_at FROM dead_letters WHERE id = :dead_letter_id"),
            {"dead_letter_id": dead_letter_id},
        )

    assert replayed_event_id == event_id
    assert dict(event) == {
        "status": "pending",
        "attempts": 0,
        "idempotency_key": idempotency_key,
        "last_error": None,
    }
    assert replayed_at is not None

    async with SessionFactory() as session:
        with pytest.raises(AppError) as error_info:
            await DeadLetterService(session).replay(dead_letter_id)

    assert error_info.value.code == "DEAD_LETTER_ALREADY_REPLAYED"
    assert error_info.value.status_code == 409
