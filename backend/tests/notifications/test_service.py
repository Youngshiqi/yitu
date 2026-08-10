from collections.abc import AsyncIterator
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from yitu.demo.seed import seed_demo_users
from yitu.notifications.models import NotificationDelivery
from yitu.notifications.service import NotificationService
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.outbox import OutboxService

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def test_from_event_is_idempotent_for_each_channel() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="payment.succeeded",
            business_id="shipment-1",
            payload={"shipment_no": "YT-1"},
            idempotency_key=f"test-{uuid4()}",
        )
        service = NotificationService(session, channels=("IN_APP", "SMS"))
        first = await service.from_event(
            event_id=event_id,
            recipient_id=recipient.id,
            template_code="PAYMENT_SUCCESS",
            template_data={"shipment_no": "YT-1"},
        )
        second = await service.from_event(
            event_id=event_id,
            recipient_id=recipient.id,
            template_code="PAYMENT_SUCCESS",
            template_data={"shipment_no": "YT-1"},
        )
        assert first.id == second.id
        deliveries = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id
                )
            )
        ).all()
        assert len(deliveries) == 2


async def test_deliver_channel_marks_pending_delivery_delivered() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="payment.succeeded",
            business_id="shipment-delivery-success",
            payload={"shipment_no": "YT-DELIVERED"},
            idempotency_key=f"test-{uuid4()}",
        )
        message = await NotificationService(session, channels=("IN_APP",)).from_event(
            event_id=event_id,
            recipient_id=recipient.id,
            template_code="PAYMENT_SUCCESS",
            template_data={"shipment_no": "YT-DELIVERED"},
        )
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.message_id == message.id
            )
        )
        assert delivery is not None

        delivered = await NotificationService(session).deliver_channel(delivery.id)

        assert delivered.status == "DELIVERED"
        assert delivered.attempts == 1
        assert delivered.delivered_at is not None
        assert delivered.last_error is None


async def test_deliver_channel_moves_to_dead_after_fifth_failure() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        recipient = next(user for user in users if user.demo_key == "customer")
        event_id = await OutboxService(session).append(
            event_type="payment.succeeded",
            business_id="shipment-delivery-dead",
            payload={"shipment_no": "YT-DEAD"},
            idempotency_key=f"test-{uuid4()}",
        )
        message = await NotificationService(session, channels=("SMS",)).from_event(
            event_id=event_id,
            recipient_id=recipient.id,
            template_code="PAYMENT_SUCCESS",
            template_data={"shipment_no": "YT-DEAD"},
        )
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.message_id == message.id
            )
        )
        assert delivery is not None

        service = NotificationService(session)
        for _ in range(5):
            failed = await service.deliver_channel(
                delivery.id,
                simulate_failure=True,
            )

        assert failed.status == "DEAD"
        assert failed.attempts == 5
        assert failed.last_error == "模拟渠道投递失败"
