"""LangGraph 使用的类型化 Agent 编排状态。"""

from operator import add
from typing import Annotated, Literal, TypedDict

AgentIntent = Literal[
    "GENERAL_CHAT",
    "KNOWLEDGE_QUERY",
    "SHIPMENT_QUERY",
    "DRAFT_UPDATE",
    "SENSITIVE_ACTION",
    "ADDRESS_QUERY",
    "IDENTITY_QUERY",
]
AgentRisk = Literal["LOW", "PERSONAL_DATA", "WRITE_ACTION", "BLOCKED"]
AgentRoute = Literal[
    "respond",
    "knowledge",
    "read_tool",
    "draft",
    "confirmation",
    "blocked",
    "address_tool",
    "identity_tool",
]


class AgentState(TypedDict, total=False):
    """保存一次图执行的编排信息，不复制业务模块中的事实。"""

    conversation_id: str
    user_id: str
    user_role: str
    user_message: str
    history: list[dict[str, str]]
    semantic_intents: list[AgentIntent]
    semantic_intent: AgentIntent
    semantic_confidence: float
    semantic_shipment_no: str | None
    semantic_knowledge_query: str | None
    semantic_draft: dict[str, object]
    requires_confirmation: bool
    clarification_question: str | None
    intent: AgentIntent
    risk: AgentRisk
    route: AgentRoute
    next_action: str
    response: str
    refusal_reason: str | None
    context_loaded: bool
    turn_count: int
    tool_call_count: int
    max_turns: int
    max_tool_calls: int
    execution_started_at: float
    timeout_seconds: float
    # 草稿 agentic loop 的输入、自研消息流（累积而非覆盖）与最终回复。
    draft_missing_fields: list[str]
    address_labels: list[str]
    draft_turns: Annotated[list[dict[str, object]], add]
    draft_response: str
