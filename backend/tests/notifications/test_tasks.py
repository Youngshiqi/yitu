from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from yitu.demo.seed import seed_demo_users
from yitu.notifications.models import NotificationDelivery, NotificationMessage
from yitu.notifications.tasks import _deliver_notifications, handle_notification_event
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.outbox import OutboxService

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def test_notification_handler_uses_consumed_outbox_event_id() -> None:
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(NotificationDelivery))
        await session.execute(delete(NotificationMessage))
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:YT-TASK",
            payload={},
            idempotency_key=f"notification:{uuid4()}",
        )

    async with SessionFactory() as session, session.begin():
        await handle_notification_event(
            session,
            event_id,
            {
                "recipient_id": str(recipient.id),
                "template_code": "PAYMENT_SUCCESS",
                "template_data": {"shipment_no": "YT-TASK"},
            },
            "notification:test",
        )

    async with SessionFactory() as session:
        message = await session.scalar(
            select(NotificationMessage).where(NotificationMessage.event_id == event_id)
        )
        deliveries = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id
                )
            )
        ).all()
        assert message is not None
        assert message.content == "运单 YT-TASK 已支付成功，等待揽收。"
        assert {delivery.channel for delivery in deliveries} == {"IN_APP", "SMS"}

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(NotificationMessage).where(NotificationMessage.event_id == event_id)
        )


async def test_deliver_notifications_task_polls_pending_deliveries() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="notification.requested",
            business_id="shipment:YT-DELIVERY-TASK",
            payload={
                "recipient_id": str(recipient.id),
                "template_code": "PAYMENT_SUCCESS",
                "template_data": {"shipment_no": "YT-DELIVERY-TASK"},
            },
            idempotency_key=f"notification:{uuid4()}",
        )
        await handle_notification_event(
            session,
            event_id,
            {
                "recipient_id": str(recipient.id),
                "template_code": "PAYMENT_SUCCESS",
                "template_data": {"shipment_no": "YT-DELIVERY-TASK"},
            },
            "notification:test",
        )

    delivered_count = await _deliver_notifications(limit=2)

    async with SessionFactory() as session:
        deliveries = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id
                )
            )
        ).all()

    assert delivered_count == 2
    assert {delivery.status for delivery in deliveries} == {"DELIVERED"}
