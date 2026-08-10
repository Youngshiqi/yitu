"""通知 SSE 事件查询和序列化。"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.notifications.models import NotificationMessage
from yitu.notifications.schemas import NotificationView
from yitu.platform.errors import AppError


async def notification_events(
    session: AsyncSession,
    recipient_id: UUID,
    *,
    last_event_id: UUID | None = None,
    after: datetime | None = None,
    limit: int = 50,
) -> AsyncIterator[str]:
    """按稳定游标返回有限通知批次和一次心跳。"""
    cursor = await validate_notification_cursor(
        session,
        recipient_id,
        last_event_id,
    )
    statement = select(NotificationMessage).where(
        NotificationMessage.recipient_id == recipient_id
    )
    if cursor is not None:
        statement = statement.where(
            or_(
                NotificationMessage.created_at > cursor.created_at,
                and_(
                    NotificationMessage.created_at == cursor.created_at,
                    NotificationMessage.id > cursor.id,
                ),
            )
        )
    elif after is not None:
        statement = statement.where(NotificationMessage.created_at > after)

    messages = (
        await session.scalars(
            statement.order_by(
                NotificationMessage.created_at, NotificationMessage.id
            ).limit(limit)
        )
    ).all()
    for message in messages:
        payload = NotificationView.model_validate(message).model_dump(mode="json")
        yield f"id: {message.id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield ": heartbeat\n\n"


async def validate_notification_cursor(
    session: AsyncSession,
    recipient_id: UUID,
    last_event_id: UUID | None,
) -> NotificationMessage | None:
    """验证 SSE 游标归属，并返回作为重连基准的通知。"""
    if last_event_id is None:
        return None
    cursor = await session.get(NotificationMessage, last_event_id)
    if cursor is None or cursor.recipient_id != recipient_id:
        raise AppError(
            code="INVALID_NOTIFICATION_CURSOR",
            message="通知游标无效",
            status_code=400,
        )
    return cursor
