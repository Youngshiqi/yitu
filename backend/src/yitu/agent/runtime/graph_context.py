"""节点通过 LangGraph Runtime 获取的请求级依赖。"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.capabilities import (
    AssistantReadService,
    ConversationMessageService,
    KnowledgeSearchService,
    ShipmentConversationService,
)
from yitu.agent.infrastructure.model_adapter import ModelAdapter
from yitu.agent.infrastructure.tracing import AgentTrace
from yitu.agent.tools.base import ToolContext
from yitu.agent.tools.knowledge import KnowledgeSearchTool
from yitu.identity.service import CurrentUser


@dataclass(frozen=True, slots=True)
class AgentRuntimeContext:
    """依赖留在 Runtime，checkpoint 中只保存可序列化工作流状态。"""

    actor_id: UUID
    request_id: str
    model: ModelAdapter
    knowledge_search_service: KnowledgeSearchService
    assistant_read_service: AssistantReadService
    shipment_conversation_service: ShipmentConversationService
    conversation_service: ConversationMessageService
    trace: AgentTrace
    history_limit: int = 20
    max_tool_calls: int = 4


def build_runtime_context(
    *,
    session: AsyncSession,
    actor: CurrentUser,
    model: ModelAdapter,
    request_id: str,
) -> AgentRuntimeContext:
    """从可信请求身份和数据库会话装配节点依赖。"""
    tool_context = ToolContext(actor=actor, session=session)
    return AgentRuntimeContext(
        actor_id=actor.id,
        request_id=request_id,
        model=model,
        knowledge_search_service=KnowledgeSearchService(
            tool=KnowledgeSearchTool(), context=tool_context, actor=actor
        ),
        assistant_read_service=AssistantReadService(context=tool_context, actor=actor),
        shipment_conversation_service=ShipmentConversationService(session, actor),
        conversation_service=ConversationMessageService(session),
        trace=AgentTrace(),
    )
