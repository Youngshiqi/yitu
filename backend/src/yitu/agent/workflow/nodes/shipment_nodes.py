"""寄件事务节点：字段草稿、报价、确认和建单均由主图显式串联。"""

from uuid import UUID

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.workflow.state import AssistantState, WorkflowError
from yitu.platform.errors import AppError


async def shipment_process_node(
    state: AssistantState, runtime: Runtime[AgentRuntimeContext]
) -> AssistantState:
    """仅处理本轮字段并重读草稿；不报价、不确认、不决定后续节点。"""
    try:
        progress = (
            await runtime.context.shipment_conversation_service.apply_user_message(
                UUID(state["conversation_id"]),
                runtime.context.actor_id,
                state.get("shipment_candidate_fields", {}),
            )
        )
    except AppError as error:
        return _app_error(error, "shipment_process_node")
    response = (
        "请继续补充："
        + "、".join(_field_label(field) for field in progress.missing_fields)
        + "。"
        if progress.missing_fields
        else "寄件信息已齐全，正在为你生成报价。"
    )
    return {"shipment_progress": progress.model_dump(mode="json"), "response": response}


async def create_quote_node(
    state: AssistantState, runtime: Runtime[AgentRuntimeContext]
) -> AssistantState:
    try:
        quote = await runtime.context.shipment_conversation_service.create_quote(
            UUID(state["conversation_id"]), runtime.context.actor_id
        )
    except AppError as error:
        return _app_error(error, "create_quote_node")
    return {"quote_progress": quote.model_dump(mode="json")}


async def shipment_confirmation_node(
    state: AssistantState, runtime: Runtime[AgentRuntimeContext]
) -> AssistantState:
    """报价后唯一的人工确认暂停点；resume 只表达选择，不直接建单。"""
    try:
        snapshot = (
            await runtime.context.shipment_conversation_service.prepare_confirmation(
                UUID(state["conversation_id"]), runtime.context.actor_id
            )
        )
    except AppError as error:
        return _app_error(error, "shipment_confirmation_node")
    decision_value = interrupt(
        {"kind": "shipment_confirmation", **snapshot.model_dump(mode="json")}
    )
    decision = str(
        decision_value.get("decision", "defer")
        if isinstance(decision_value, dict)
        else decision_value
    ).lower()
    update: AssistantState = {"confirmation_snapshot": snapshot.model_dump(mode="json")}
    if decision == "confirm":
        update["shipment_requested"] = True
        update["shipment_candidate_fields"] = {"_confirmed": True}
    else:
        update["response"] = (
            "已取消本次寄件确认，不会创建运单。"
            if decision == "cancel"
            else "已暂缓本次寄件确认，你可以继续咨询其他问题。"
        )
    return update


async def create_shipment_node(
    state: AssistantState, runtime: Runtime[AgentRuntimeContext]
) -> AssistantState:
    try:
        receipt = await runtime.context.shipment_conversation_service.create_confirmed_shipment(
            UUID(state["conversation_id"]),
            runtime.context.actor_id,
            runtime.context.request_id,
        )
    except AppError as error:
        return _app_error(error, "create_shipment_node")
    return {
        "response": f"运单 {receipt.shipment_no} 已创建，待支付 {receipt.total_cents / 100:.2f} 元。"
    }


def _app_error(error: AppError, source_node: str) -> AssistantState:
    return {
        "error": WorkflowError(
            code=error.code, message=error.message, source_node=source_node
        ).model_dump(mode="json")
    }


def _field_label(field: str) -> str:
    return {
        "sender_address_id": "寄件地址",
        "receiver_address_id": "收件地址",
        "estimated_weight_grams": "包裹重量",
        "estimated_length_cm": "长度",
        "estimated_width_cm": "宽度",
        "estimated_height_cm": "高度",
        "package_category": "物品类型",
        "package_description": "物品内容",
    }.get(field, field)
