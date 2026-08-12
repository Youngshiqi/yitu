"""Agent 会话持久化和模型调用服务。"""

from time import monotonic
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.graph import build_agent_graph
from yitu.agent.model_adapter import ModelAdapter, ModelMessage, ModelUnavailableError
from yitu.agent.models import AgentConversation, AgentMessage
from yitu.agent.schemas import AgentTurnView, MessageView
from yitu.agent.state import AgentState
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
        graph_result = await build_agent_graph().ainvoke(
            self._initial_graph_state(conversation.id, actor, content, history)
        )
        if graph_result.get("route") == "respond":
            try:
                reply = await model.complete(
                    [
                        ModelMessage(role=item.role, content=item.content)
                        for item in history
                    ]
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
        else:
            # 未接入的工具分支只返回图生成的安全动作，不让模型伪造业务结果。
            reply = graph_result.get("response", "请求已进入受控处理流程。")

        assistant_message = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            envelope={
                "intent": graph_result.get("intent"),
                "risk": graph_result.get("risk"),
                "route": graph_result.get("route"),
                "next_action": graph_result.get("next_action"),
            },
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

    @staticmethod
    def _initial_graph_state(
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        history: list[AgentMessage],
    ) -> AgentState:
        """从可信身份和持久化历史构造有界图状态。"""
        return {
            "conversation_id": str(conversation_id),
            "user_id": str(actor.id),
            "user_role": actor.role.value,
            "user_message": content,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
            "turn_count": 0,
            "tool_call_count": 0,
            "max_turns": 8,
            "max_tool_calls": 4,
            "execution_started_at": monotonic(),
            "timeout_seconds": 30.0,
        }

    async def _load_messages(self, conversation_id: UUID) -> list[AgentMessage]:
        statement = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
        )
        return list((await self._session.scalars(statement)).all())
