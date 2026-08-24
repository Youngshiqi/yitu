"""七节点助手主图的 checkpoint 状态。"""

from typing import TypedDict


class AssistantState(TypedDict, total=False):
    """只保存工作流快照；身份和数据库会话由 Runtime context 注入。"""

    conversation_id: str
    user_message: str
    messages: list[dict[str, object]]
    response: str
    pending_tool_calls: list[dict[str, object]]
    shipment_handoff: dict[str, object]
    shipment_result: dict[str, object]
    error: dict[str, object]
    turn_count: int
    tool_call_count: int
