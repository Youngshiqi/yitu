"""Agent 持久化消息的 SSE 查询和序列化。"""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.models import AgentMessage
from yitu.agent.schemas import MessageView
from yitu.platform.errors import AppError


def encode_agent_event(event: str, payload: dict[str, object]) -> str:
    """把流式 Agent 事件编码为标准 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def agent_message_events(
    session: AsyncSession,
    conversation_id: UUID,
    *,
    last_event_id: UUID | None = None,
    limit: int = 100,
) -> AsyncIterator[str]:
    """按稳定游标返回有限消息批次，避免长连接无限占用数据库会话。"""
    cursor = await validate_agent_cursor(session, conversation_id, last_event_id)
    statement = select(AgentMessage).where(
        AgentMessage.conversation_id == conversation_id
    )
    if cursor is not None:
        statement = statement.where(
            or_(
                AgentMessage.created_at > cursor.created_at,
                and_(
                    AgentMessage.created_at == cursor.created_at,
                    AgentMessage.id > cursor.id,
                ),
            )
        )
    messages = (
        await session.scalars(
            statement.order_by(AgentMessage.created_at, AgentMessage.id).limit(limit)
        )
    ).all()
    for message in messages:
        payload = MessageView.model_validate(message).model_dump(mode="json")
        yield (
            f"id: {message.id}\n"
            "event: message\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        )
    yield ": heartbeat\n\n"


async def validate_agent_cursor(
    session: AsyncSession,
    conversation_id: UUID,
    last_event_id: UUID | None,
) -> AgentMessage | None:
    """验证事件游标属于当前会话，阻止跨会话读取。"""
    if last_event_id is None:
        return None
    cursor = await session.get(AgentMessage, last_event_id)
    if cursor is None or cursor.conversation_id != conversation_id:
        raise AppError(
            code="INVALID_AGENT_CURSOR",
            message="Agent 消息游标无效",
            status_code=400,
        )
    return cursor
