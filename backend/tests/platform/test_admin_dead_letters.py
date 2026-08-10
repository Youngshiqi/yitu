from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.exceptions.test_api import _headers
from yitu.identity.models import Role
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.outbox import OutboxService

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_dead_letter() -> tuple[UUID, UUID]:
    dead_letter_id = uuid4()
    async with SessionFactory() as session, session.begin():
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:admin-dead-letter",
            payload={"shipment_id": "admin-dead-letter"},
            idempotency_key=f"notification:{uuid4()}",
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
                ":id, :event_id, 'notification.requested', 'shipment:admin-dead-letter', "
                "CAST('{\"shipment_id\":\"admin-dead-letter\"}' AS JSONB), "
                "'notification:admin-dead-letter', 5, '模拟失败', CURRENT_TIMESTAMP, "
                "'修复后重放'"
                ")"
            ),
            {"id": dead_letter_id, "event_id": event_id},
        )
    return dead_letter_id, event_id


async def test_system_admin_can_list_and_replay_dead_letter_via_api() -> None:
    dead_letter_id, event_id = await _seed_dead_letter()
    system_admin = uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        forbidden = await client.get(
            "/api/v1/admin/dead-letters",
            headers=_headers(uuid4(), Role.OPERATIONS_ADMIN),
        )
        listed = await client.get(
            "/api/v1/admin/dead-letters",
            headers=_headers(system_admin, Role.SYSTEM_ADMIN),
        )
        replay = await client.post(
            f"/api/v1/admin/dead-letters/{dead_letter_id}/replay",
            headers=_headers(system_admin, Role.SYSTEM_ADMIN),
        )

    assert forbidden.status_code == 403
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == str(dead_letter_id)
    assert replay.status_code == 200, replay.text
    assert replay.json() == {
        "dead_letter_id": str(dead_letter_id),
        "event_id": str(event_id),
        "status": "pending",
    }

    async with SessionFactory() as session:
        status = await session.scalar(
            text("SELECT status FROM outbox_events WHERE id = :event_id"),
            {"event_id": event_id},
        )
    assert status == "pending"
