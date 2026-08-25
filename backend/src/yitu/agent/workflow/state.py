"""七节点助手主图的 checkpoint 状态。"""

from typing import TypedDict

from yitu.agent.workflow.contracts import (
    AssistantToolCall,
    AssistantToolObservation,
    ConfirmationSnapshot,
    DraftProgress,
    DraftToolCall,
    KnowledgeEvidence,
    KnowledgeSearchInput,
    QuoteProgress,
    ShipmentReceipt,
    WorkflowError,
)


class AssistantState(TypedDict, total=False):
    """只保存工作流快照；身份和数据库会话由 Runtime context 注入。"""

    conversation_id: str
    user_message: str
    messages: list[dict[str, object]]
    response: str
    pending_tool_calls: list[dict[str, object]]
    # 仅保存本轮由主 Agent 提取的候选字段。寄件不再启动独立子图。
    shipment_requested: bool
    shipment_candidate_fields: dict[str, object]
    shipment_progress: dict[str, object]
    quote_progress: dict[str, object]
    confirmation_snapshot: dict[str, object]
    error: dict[str, object]
    turn_count: int
    tool_call_count: int


__all__ = [
    "AssistantState",
    "AssistantToolCall",
    "AssistantToolObservation",
    "ConfirmationSnapshot",
    "DraftProgress",
    "DraftToolCall",
    "KnowledgeEvidence",
    "KnowledgeSearchInput",
    "QuoteProgress",
    "ShipmentReceipt",
    "WorkflowError",
]
