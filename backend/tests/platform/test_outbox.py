from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from yitu.platform.clock import Clock
from yitu.platform.database import SessionFactory, transactional_session
from yitu.platform.outbox import OutboxService


class FixedClock(Clock):
    @staticmethod
    def now() -> datetime:
        return datetime(2026, 8, 9, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


async def test_business_fact_and_outbox_event_roll_back_together() -> None:
    request_id = str(uuid4())
    event_id: UUID | None = None

    with pytest.raises(RuntimeError, match="主动回滚"):
        async with transactional_session() as session:
            await session.execute(
                text(
                    "INSERT INTO audit_entries ("
                    "actor, action, resource, request_id, created_at"
                    ") VALUES ("
                    "'system', 'probe.create', 'probe:1', :request_id, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"request_id": request_id},
            )
            event_id = await OutboxService(session, clock=FixedClock()).append(
                event_type="probe.created",
                business_id="probe:1",
                payload={"probe_id": 1},
                idempotency_key=f"probe:{request_id}",
            )
            in_transaction_count = await session.scalar(
                text("SELECT count(*) FROM outbox_events WHERE id = :event_id"),
                {"event_id": event_id},
            )
            assert in_transaction_count == 1
            raise RuntimeError("主动回滚")

    assert event_id is not None
    async with SessionFactory() as session:
        audit_count = await session.scalar(
            text("SELECT count(*) FROM audit_entries WHERE request_id = :request_id"),
            {"request_id": request_id},
        )
        event_count = await session.scalar(
            text("SELECT count(*) FROM outbox_events WHERE id = :event_id"),
            {"event_id": event_id},
        )

    assert audit_count == 0
    assert event_count == 0
