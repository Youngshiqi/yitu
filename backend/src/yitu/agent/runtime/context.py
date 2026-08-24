"""节点通过 LangGraph Runtime 获取的请求级依赖。"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.adapters import (
    AgentTraceAdapter,
    AssistantReadAdapter,
    KnowledgeAdapter,
    ModelAdapterPort,
    ShipmentWorkflowAdapter,
    SqlAlchemyConversationAdapter,
)
from yitu.agent.model_adapter import ModelAdapter
from yitu.agent.ports import (
    AssistantReadPort,
    ConversationPort,
    KnowledgePort,
    ModelPort,
    ShipmentWorkflowPort,
    TracePort,
)
from yitu.agent.tools.base import ToolContext
from yitu.agent.tools.knowledge import KnowledgeSearchTool
from yitu.agent.tracing import AgentTrace
from yitu.identity.service import CurrentUser


@dataclass(frozen=True, slots=True)
class AgentRuntimeContext:
    """依赖留在 Runtime，checkpoint 中只保存可序列化工作流状态。"""

    actor_id: UUID
    request_id: str
    model: ModelPort
    knowledge: KnowledgePort
    assistant_reads: AssistantReadPort
    shipment: ShipmentWorkflowPort
    conversation: ConversationPort
    trace: TracePort
    history_limit: int = 20
    max_agent_turns: int = 8
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
        model=ModelAdapterPort(model),
        knowledge=KnowledgeAdapter(
            tool=KnowledgeSearchTool(), context=tool_context, actor=actor
        ),
        assistant_reads=AssistantReadAdapter(context=tool_context, actor=actor),
        shipment=ShipmentWorkflowAdapter(session=session, actor=actor),
        conversation=SqlAlchemyConversationAdapter(session),
        trace=AgentTraceAdapter(AgentTrace()),
    )
