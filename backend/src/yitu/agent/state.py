"""LangGraph 使用的类型化 Agent 编排状态。"""

from typing import Literal, TypedDict

AgentIntent = Literal[
    "GENERAL_CHAT",
    "KNOWLEDGE_QUERY",
    "SHIPMENT_QUERY",
    "DRAFT_UPDATE",
    "SENSITIVE_ACTION",
]
AgentRisk = Literal["LOW", "PERSONAL_DATA", "WRITE_ACTION", "BLOCKED"]
AgentRoute = Literal[
    "respond",
    "knowledge",
    "read_tool",
    "draft",
    "confirmation",
    "blocked",
]


class AgentState(TypedDict, total=False):
    """保存一次图执行的编排信息，不复制业务模块中的事实。"""

    conversation_id: str
    user_id: str
    user_role: str
    user_message: str
    history: list[dict[str, str]]
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
