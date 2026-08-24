"""八节点寄件子图的独立 checkpoint 状态。"""

from typing import TypedDict


class ShipmentState(TypedDict, total=False):
    """子图不继承主图 State，只接收 handoff 并返回 workflow_result。"""

    conversation_id: str
    handoff: dict[str, object]
    messages: list[dict[str, object]]
    draft_progress: dict[str, object]
    pending_tool_calls: list[dict[str, object]]
    quote_progress: dict[str, object]
    confirmation_snapshot: dict[str, object]
    confirmation_decision: str
    draft_ready: bool
    draft_validated: bool
    workflow_result: dict[str, object]
    error: dict[str, object]
    turn_count: int
    tool_call_count: int
