"""通知查询和 SSE 接口。"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser, get_current_user
from yitu.notifications.models import NotificationMessage
from yitu.notifications.schemas import NotificationView
from yitu.notifications.sse import notification_events, validate_notification_cursor
from yitu.platform.clock import Clock, to_business_timezone
from yitu.platform.database import get_session
from yitu.platform.errors import AppError

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)
_notification_after = Query(default=None)
_last_event_id = Header(default=None, alias="Last-Event-ID")


@router.get("", response_model=list[NotificationView])
async def list_notifications(
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
    unread_only: bool = Query(default=False),
) -> list[NotificationMessage]:
    """列出当前客户自己的通知。"""
    statement = select(NotificationMessage).where(NotificationMessage.recipient_id == user.id)
    if unread_only:
        statement = statement.where(NotificationMessage.status == "UNREAD")
    return list((await session.scalars(statement.order_by(NotificationMessage.created_at.desc()))).all())


@router.post("/{notification_id}/read", response_model=NotificationView)
async def mark_read(
    notification_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> NotificationMessage:
    """将当前客户自己的通知标记为已读。"""
    notification = await session.get(NotificationMessage, notification_id)
    if notification is None or notification.recipient_id != user.id:
        raise AppError(code="NOTIFICATION_NOT_FOUND", message="通知不存在", status_code=404)
    notification.status = "READ"
    notification.read_at = to_business_timezone(Clock.now())
    await session.commit()
    return notification


@router.get("/stream")
async def notification_stream(
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
    after: datetime | None = _notification_after,
    last_event_id: UUID | None = _last_event_id,
) -> StreamingResponse:
    """返回有限通知批次和心跳，支持标准 Last-Event-ID 重连。"""
    await validate_notification_cursor(session, user.id, last_event_id)
    events = notification_events(
        session,
        user.id,
        last_event_id=last_event_id,
        after=after,
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
