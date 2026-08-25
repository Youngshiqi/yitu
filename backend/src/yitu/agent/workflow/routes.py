"""主图所有条件边的集中定义。

节点只负责读取输入、调用能力和写回 State；本文件负责决定下一个节点。
"""

from yitu.agent.workflow.state import AssistantState


def security_result_route(state: AssistantState) -> str:
    return "handle_failure_node" if state.get("error") else "assistant_agent_node"


def assistant_action_route(state: AssistantState) -> str:
    if state.get("error"):
        return "handle_failure_node"
    if state.get("shipment_requested"):
        return "shipment_process_node"
    if state.get("pending_tool_calls"):
        return "assistant_tools_node"
    return "finalize_turn_node"


def assistant_tools_route(state: AssistantState) -> str:
    return "handle_failure_node" if state.get("error") else "assistant_agent_node"


def shipment_progress_route(state: AssistantState) -> str:
    if state.get("error"):
        return "handle_failure_node"
    progress = state.get("shipment_progress", {})
    return (
        "finalize_turn_node" if progress.get("missing_fields") else "create_quote_node"
    )


def quote_route(state: AssistantState) -> str:
    return "handle_failure_node" if state.get("error") else "shipment_confirmation_node"


def confirmation_route(state: AssistantState) -> str:
    if state.get("error"):
        return "handle_failure_node"
    return (
        "create_shipment_node"
        if state.get("shipment_candidate_fields", {}).get("_confirmed")
        else "finalize_turn_node"
    )


def creation_route(state: AssistantState) -> str:
    return "handle_failure_node" if state.get("error") else "finalize_turn_node"
