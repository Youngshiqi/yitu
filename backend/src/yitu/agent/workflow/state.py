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

    conversation_id: str # 会话 ID，也是Langgraph thread_id
    user_message: str # 本轮用户输入
    messages: list[dict[str, object]] # 对话历史
    response: str # 最终回复文本
    pending_tool_calls: list[dict[str, object]] # 待执行的工具调用
    # 仅保存本轮由主 Agent 提取的候选字段。寄件不再启动独立子图。
    shipment_requested: bool  # 标记：本轮是否触发寄件流程
    shipment_candidate_fields: dict[str, object] # 从用户消息中提取的寄件字段
    shipment_progress: dict[str, object] # 寄件草稿进度
    quote_progress: dict[str, object] # 报价进度
    confirmation_snapshot: dict[str, object] # 确认快照
    error: dict[str, object] # WorkflowError 序列化


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
