"""节点通过 LangGraph Runtime 获取的请求级依赖。"""

from dataclasses import dataclass
from uuid import UUID

from yitu.agent.ports import (
    AssistantReadPort,
    ConversationPort,
    KnowledgePort,
    ModelPort,
    ShipmentWorkflowPort,
    TracePort,
)


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
