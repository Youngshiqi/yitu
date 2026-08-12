"""Agent 会话持久化和模型调用服务。"""

from time import monotonic
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.context import build_model_context
from yitu.agent.graph import build_agent_graph
from yitu.agent.model_adapter import ModelAdapter, ModelMessage, ModelUnavailableError
from yitu.agent.models import AgentConversation, AgentMemory, AgentMessage
from yitu.agent.schemas import AgentTurnView, MessageView
from yitu.agent.state import AgentState
from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.agent.tools.knowledge import KnowledgeSearchInput, KnowledgeSearchTool
from yitu.agent.tools.shipments import ShipmentReadInput, ShipmentReadTool
from yitu.agent.tracing import AgentTrace
from yitu.identity.service import CurrentUser
from yitu.platform.audit import AuditService
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
        trace = AgentTrace()
        trace.record("message.received", role="user")
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
        memories = await self._load_memories(actor.id)
        graph_result = await build_agent_graph().ainvoke(
            self._initial_graph_state(conversation.id, actor, content, history)
        )
        trace.record(
            "graph.routed",
            route=graph_result.get("route"),
            intent=graph_result.get("intent"),
            risk=graph_result.get("risk"),
        )
        tool_result: ToolResult[BaseModel] | None = None
        route = graph_result.get("route")
        if route == "knowledge":
            tool_result = await KnowledgeSearchTool().execute(
                KnowledgeSearchInput(query=content),
                ToolContext(actor=actor, session=self._session),
            )
            reply = self._knowledge_reply(tool_result)
            trace.record("tool.knowledge", found=tool_result.found)
        elif route == "read_tool":
            tool_result = await ShipmentReadTool().execute(
                ShipmentReadInput(shipment_no=_extract_shipment_no(content)),
                ToolContext(actor=actor, session=self._session),
            )
            reply = self._shipment_reply(tool_result)
            trace.record("tool.shipment", found=tool_result.found)
        elif route == "respond":
            try:
                reply = await model.complete(build_model_context(
                    [ModelMessage(role=item.role, content=item.content) for item in history],
                    memories,
                ))
                trace.record("model.completed")
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
                "trace_id": str(trace.trace_id),
                "intent": graph_result.get("intent"),
                "risk": graph_result.get("risk"),
                "route": route,
                "next_action": graph_result.get("next_action"),
                "tool_result": tool_result.model_dump(mode="json")
                if tool_result is not None
                else None,
                "trace": trace.summary(),
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
    def _knowledge_reply(result: ToolResult[BaseModel]) -> str:
        """将 RAG 结果转为谨慎摘要，完整证据保留在结构化信封。"""
        if not result.found:
            return "暂未找到足够的已发布知识证据，无法确认该规则。"
        return "已找到已发布物流知识证据，请结合消息中的引用查看原文。"

    @staticmethod
    def _shipment_reply(result: ToolResult[BaseModel]) -> str:
        """将本人运单工具结果转为不泄漏额外个人信息的摘要。"""
        if not result.found:
            return "没有找到当前登录用户有权访问的运单。"
        return "已读取你的运单、轨迹、费用和 ETA 信息。"

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

    async def delete_conversation(self, conversation_id: UUID, actor: CurrentUser, request_id: str) -> None:
        """删除会话正文和关联草稿/授权，保留不含正文的匿名审计记录。"""
        conversation = await self.get_owned(conversation_id, actor)
        await AuditService(self._session).record(
            actor=str(actor.id), action="agent.conversation.deleted",
            resource="agent-conversation:anonymous", before_summary={"conversation_id": str(conversation.id)},
            after_summary={"deleted": True}, reason="user_requested", request_id=request_id,
        )
        await self._session.delete(conversation)
        await self._session.flush()

    async def _load_memories(self, owner_id: UUID) -> list[str]:
        rows = await self._session.scalars(
            select(AgentMemory).where(AgentMemory.owner_id == owner_id, AgentMemory.active.is_(True))
        )
        now = Clock.now()
        return [row.content for row in rows.all() if row.expires_at is None or row.expires_at > now]


def _extract_shipment_no(content: str) -> str | None:
    """仅提取显式 YT 运单号；未提供时由服务返回最近一票本人运单。"""
    import re

    match = re.search(r"\bYT[A-Z0-9]{4,32}\b", content.upper())
    return match.group(0) if match else None
