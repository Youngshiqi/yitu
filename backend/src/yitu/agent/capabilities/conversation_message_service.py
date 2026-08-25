"""Agent 会话消息的 SQLAlchemy 持久化适配器。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.models import AgentConversation, AgentMessage
from yitu.agent.schemas import MessageView
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError


class ConversationMessageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_history(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        await self._get_owned(conversation_id, actor_id)
        rows = (
            await self._session.scalars(
                select(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
                .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
                .limit(limit)
            )
        ).all()
        return [
            {"role": row.role, "content": row.content, "envelope": row.envelope}
            for row in reversed(rows)
        ]

    async def append_message(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        *,
        role: str,
        content: str,
        envelope: dict[str, object] | None = None,
    ) -> dict[str, object]:
        conversation = await self._get_owned(conversation_id, actor_id)
        now = Clock.now()
        message = AgentMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            envelope=envelope,
            created_at=now,
        )
        self._session.add(message)
        conversation.updated_at = now
        if role == "user" and not conversation.title:
            conversation.title = content.strip()[:32] or "新会话"
        await self._session.flush()
        return MessageView.model_validate(message).model_dump(mode="json")

    async def _get_owned(
        self, conversation_id: UUID, actor_id: UUID
    ) -> AgentConversation:
        conversation = await self._session.get(AgentConversation, conversation_id)
        if conversation is None or conversation.owner_id != actor_id:
            raise AppError("AGENT_CONVERSATION_NOT_FOUND", "Agent 会话不存在", 404)
        return conversation
