from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from yitu.demo.seed import DEMO_PASSWORD, seed_demo_users
from yitu.main import create_app
from yitu.notifications.models import NotificationMessage
from yitu.notifications.sse import notification_events
from yitu.platform.config import get_settings
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.outbox import OutboxService

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    await dispose_database()
    yield
    await dispose_database()


async def test_sse_reconnect_cursor_excludes_delivered_message() -> None:
    created_at = datetime(2099, 8, 10, 12, 0, tzinfo=TZ)
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_ids = [
            await OutboxService(session).append(
                event_type="notification.requested",
                business_id=f"shipment:{shipment_no}",
                payload={
                    "recipient_id": str(recipient.id),
                    "template_code": "PAYMENT_SUCCESS",
                    "template_data": {"shipment_no": shipment_no},
                },
                idempotency_key=f"notification:{shipment_no}:{uuid4()}",
            )
            for shipment_no in ("YT-SSE-1", "YT-SSE-2")
        ]
        messages = [
            NotificationMessage(
                event_id=event_id,
                recipient_id=recipient.id,
                template_code="PAYMENT_SUCCESS",
                template_data={"shipment_no": shipment_no},
                title="支付成功",
                content=f"运单 {shipment_no} 已支付成功，等待揽收。",
                status="UNREAD",
                created_at=created_at,
            )
            for event_id, shipment_no in zip(
                event_ids,
                ("YT-SSE-1", "YT-SSE-2"),
                strict=True,
            )
        ]
        session.add_all(messages)
        await session.flush()
        ordered_messages = (
            await session.execute(
                select(NotificationMessage.id, NotificationMessage.content)
                .where(NotificationMessage.event_id.in_(event_ids))
                .order_by(NotificationMessage.created_at, NotificationMessage.id)
            )
        ).all()
        (first_id, _first_content), (second_id, second_content) = ordered_messages

    async with SessionFactory() as session:
        events = [
            event
            async for event in notification_events(
                session, recipient.id, last_event_id=first_id
            )
        ]

    second_event = next(event for event in events if f"id: {second_id}" in event)
    assert second_content in second_event
    assert all(f"id: {first_id}" not in event for event in events)
    assert events[-1] == ": heartbeat\n\n"

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(NotificationMessage).where(
                NotificationMessage.event_id.in_([message.event_id for message in messages])
            )
        )


async def test_notification_stream_returns_sse_for_authenticated_user() -> None:
    created_at = datetime(2099, 8, 10, 13, 0, tzinfo=TZ)
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:YT-SSE-HTTP",
            payload={
                "recipient_id": str(recipient.id),
                "template_code": "PAYMENT_SUCCESS",
                "template_data": {"shipment_no": "YT-SSE-HTTP"},
            },
            idempotency_key=f"notification:http:{uuid4()}",
        )
        message = NotificationMessage(
            event_id=event_id,
            recipient_id=recipient.id,
            template_code="PAYMENT_SUCCESS",
            template_data={"shipment_no": "YT-SSE-HTTP"},
            title="支付成功",
            content="运单 YT-SSE-HTTP 已支付成功，等待揽收。",
            status="UNREAD",
            created_at=created_at,
        )
        session.add(message)
        await session.flush()
        message_id = message.id

    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            login = await client.post(
                "/api/v1/auth/demo-login",
                json={"login_name": "customer.demo", "password": DEMO_PASSWORD},
            )
            assert login.status_code == 200, login.text
            response = await client.get(
                "/api/v1/notifications/stream",
                headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                params={"after": "2099-08-10T12:59:00+08:00"},
            )
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"id: {message_id}" in response.text
    assert "YT-SSE-HTTP" in response.text
    assert response.text.endswith(": heartbeat\n\n")


async def test_notification_stream_rejects_unknown_last_event_id() -> None:
    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)

    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            login = await client.post(
                "/api/v1/auth/demo-login",
                json={"login_name": "customer.demo", "password": DEMO_PASSWORD},
            )
            assert login.status_code == 200, login.text
            response = await client.get(
                "/api/v1/notifications/stream",
                headers={
                    "Authorization": f"Bearer {login.json()['access_token']}",
                    "Last-Event-ID": str(uuid4()),
                },
            )
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_NOTIFICATION_CURSOR"
