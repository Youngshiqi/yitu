"""Agent 会话持久化和模型调用服务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.model_adapter import ModelAdapter, ModelMessage, ModelUnavailableError
from yitu.agent.models import AgentConversation, AgentMessage
from yitu.agent.schemas import AgentTurnView, MessageView
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError


class AgentConversationService:
    """维护用户隔离的会话历史，并协调可替换模型适配器。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, actor: CurrentUser, *, title: str | None = None
    ) -> AgentConversation:
        now = Clock.now()
        conversation = AgentConversation(
            owner_id=actor.id,
            title=title,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self._session.add(conversation)
        await self._session.commit()
        return conversation

    async def list_conversations(
        self, actor: CurrentUser
    ) -> list[AgentConversation]:
        statement = (
            select(AgentConversation)
            .where(AgentConversation.owner_id == actor.id)
            .order_by(AgentConversation.updated_at.desc(), AgentConversation.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_owned(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> AgentConversation:
        conversation = await self._session.get(AgentConversation, conversation_id)
        if conversation is None or conversation.owner_id != actor.id:
            # 统一返回不存在，避免通过 ID 探测其他用户会话。
            raise AppError(
                code="AGENT_CONVERSATION_NOT_FOUND",
                message="Agent 会话不存在",
                status_code=404,
            )
        return conversation

    async def list_messages(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> list[AgentMessage]:
        await self.get_owned(conversation_id, actor)
        return await self._load_messages(conversation_id)

    async def send_message(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        model: ModelAdapter,
    ) -> AgentTurnView:
        conversation = await self.get_owned(conversation_id, actor)
        now = Clock.now()
        user_message = AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content=content,
            envelope=None,
            created_at=now,
        )
        self._session.add(user_message)
        conversation.updated_at = now
        await self._session.commit()

        history = await self._load_messages(conversation.id)
        try:
            reply = await model.complete(
                [ModelMessage(role=item.role, content=item.content) for item in history]
            )
        except ModelUnavailableError as error:
            # 用户消息已单独提交，服务恢复后可以从同一会话继续重试。
            conversation.status = "WAITING_RETRY"
            conversation.updated_at = Clock.now()
            await self._session.commit()
            raise AppError(
                code="AGENT_MODEL_UNAVAILABLE",
                message="AI 服务暂时不可用，会话消息已保存，请稍后重试",
                status_code=503,
            ) from error

        assistant_message = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            envelope=None,
            created_at=Clock.now(),
        )
        self._session.add(assistant_message)
        conversation.status = "ACTIVE"
        conversation.updated_at = assistant_message.created_at
        await self._session.commit()
        return AgentTurnView(
            user_message=MessageView.model_validate(user_message),
            assistant_message=MessageView.model_validate(assistant_message),
        )

    async def _load_messages(self, conversation_id: UUID) -> list[AgentMessage]:
        statement = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
        )
        return list((await self._session.scalars(statement)).all())
