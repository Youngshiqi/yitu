"""通知 Outbox 消费和渠道投递任务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.notifications.models import NotificationDelivery
from yitu.notifications.service import NotificationService
from yitu.platform.database import SessionFactory
from yitu.platform.tasks import register_event_handler
from yitu.worker import celery_app, run_async


def _uuid(value: object, name: str) -> UUID:
    if not isinstance(value, str):
        raise TypeError(f"通知事件缺少 {name}")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"通知事件的 {name} 无效") from error


async def handle_notification_event(
    session: AsyncSession,
    event_id: UUID,
    payload: dict[str, object],
    idempotency_key: str,
) -> None:
    """将 notification.requested 事件物化为通知和渠道记录。"""
    del idempotency_key
    recipient_id = _uuid(payload.get("recipient_id"), "recipient_id")
    template_code = payload.get("template_code")
    template_data = payload.get("template_data", {})
    if not isinstance(template_code, str) or not isinstance(template_data, dict):
        raise TypeError("通知事件模板数据无效")
    await NotificationService(session).from_event(
        event_id=event_id,
        recipient_id=recipient_id,
        template_code=template_code,
        template_data=template_data,
    )


register_event_handler("notification.requested", handle_notification_event)


@celery_app.task(name="yitu.deliver_notifications")  # type: ignore[untyped-decorator]
def deliver_notifications(limit: int = 100) -> int:
    """投递一批待处理的通知渠道记录。"""
    return run_async(_deliver_notifications(limit))


async def _deliver_notifications(limit: int) -> int:
    async with SessionFactory() as session, session.begin():
        deliveries = (
            await session.scalars(
                select(NotificationDelivery)
                .where(NotificationDelivery.status.in_(("PENDING", "FAILED")))
                .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for delivery in deliveries:
            await NotificationService(session).deliver_channel(delivery.id)
        return len(deliveries)
