"""寄件子图的草稿 ReAct 循环、确定性报价和人工确认节点。"""

import json
from uuid import UUID

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import ValidationError

from yitu.agent.model_adapter import ModelMessage, ToolCall
from yitu.agent.prompts import BUDGET_REFUSAL, DRAFT_LOOP_PROMPT
from yitu.agent.runtime.context import AgentRuntimeContext
from yitu.agent.tools.drafts import UPDATE_DRAFT_TOOL_SPECS
from yitu.agent.workflow_state import (
    DraftProgress,
    DraftToolCall,
    ShipmentHandoff,
    ShipmentState,
    ShipmentWorkflowResult,
    WorkflowError,
)
from yitu.platform.errors import AppError

_INSPECT_DRAFT_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "inspect_draft",
        "description": "重新读取当前寄件草稿、缺失字段和版本。",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}
DRAFT_TOOL_SPECS: tuple[dict[str, object], ...] = (
    _INSPECT_DRAFT_TOOL,
    *UPDATE_DRAFT_TOOL_SPECS,
)


async def load_draft_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    conversation_id = UUID(state["conversation_id"])
    progress = await runtime.context.shipment.load_progress(
        conversation_id, runtime.context.actor_id
    )
    messages = list(state.get("messages", []))
    if not messages:
        handoff = ShipmentHandoff.model_validate(state["handoff"])
        messages.append(
            {
                "role": "user",
                "content": handoff.user_message,
                "handoff_fields": handoff.extracted_fields,
            }
        )
    runtime.context.trace.record("draft.loaded", revision=progress.revision)
    return {
        "draft_progress": progress.model_dump(mode="json"),
        "messages": messages,
        "turn_count": state.get("turn_count", 0),
        "tool_call_count": state.get("tool_call_count", 0),
    }


async def draft_agent_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    turn_count = state.get("turn_count", 0)
    if turn_count >= runtime.context.max_agent_turns:
        return _workflow_error("AGENT_BUDGET_EXCEEDED", BUDGET_REFUSAL, "draft_agent_node")
    progress = DraftProgress.model_validate(state["draft_progress"])
    prompt = DRAFT_LOOP_PROMPT.format(
        filled_fields=json.dumps(progress.snapshot, ensure_ascii=False),
        missing_fields="、".join(progress.missing_fields) or "无",
        address_labels="由 inspect_draft 工具按当前身份读取",
    )
    result = None
    async for event in runtime.context.model.stream_with_tools(
        [ModelMessage(role="system", content=prompt), *_model_messages(state.get("messages", []))],
        DRAFT_TOOL_SPECS,
    ):
        if event.delta:
            runtime.stream_writer({"type": "token", "content": event.delta})
        if event.result is not None:
            result = event.result
    if result is None:
        return _workflow_error(
            "MODEL_EMPTY_RESULT", "模型没有返回草稿处理结果", "draft_agent_node", True
        )
    messages = list(state.get("messages", []))
    assistant_message: dict[str, object] = {
        "role": "assistant",
        "content": result.content or "",
    }
    if result.tool_calls:
        assistant_message["tool_calls"] = [_tool_call_dict(call) for call in result.tool_calls]
    messages.append(assistant_message)
    update: ShipmentState = {"messages": messages, "turn_count": turn_count + 1}
    if result.tool_calls:
        update["pending_tool_calls"] = [_tool_call_dict(call) for call in result.tool_calls]
    elif progress.missing_fields:
        workflow_result = ShipmentWorkflowResult(
            status="NEEDS_INPUT",
            response=(result.content or "请继续补充寄件信息。").strip(),
        )
        update["workflow_result"] = workflow_result.model_dump(mode="json")
    else:
        update["draft_ready"] = True
    runtime.context.trace.record(
        "draft.decided", tool_call_count=len(result.tool_calls)
    )
    return update


async def draft_tools_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    raw_calls = state.get("pending_tool_calls", [])
    current_count = state.get("tool_call_count", 0)
    if current_count + len(raw_calls) > runtime.context.max_tool_calls:
        return _workflow_error("AGENT_BUDGET_EXCEEDED", BUDGET_REFUSAL, "draft_tools_node")
    conversation_id = UUID(state["conversation_id"])
    messages = list(state.get("messages", []))
    progress = DraftProgress.model_validate(state["draft_progress"])
    try:
        for raw_call in raw_calls:
            call = DraftToolCall.model_validate(raw_call)
            progress = await runtime.context.shipment.execute_draft_tool(
                conversation_id,
                runtime.context.actor_id,
                call,
            )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        progress.model_dump(mode="json"), ensure_ascii=False
                    ),
                    "tool_call_id": call.id,
                }
            )
            runtime.context.trace.record("draft.tool_completed", tool=call.name)
    except ValidationError:
        return _workflow_error(
            "DRAFT_TOOL_ARGUMENT_INVALID",
            "模型请求了无效或未授权的草稿工具参数",
            "draft_tools_node",
        )
    except AppError as error:
        return _app_error(error, "draft_tools_node")
    return {
        "messages": messages,
        "draft_progress": progress.model_dump(mode="json"),
        "pending_tool_calls": [],
        "tool_call_count": current_count + len(raw_calls),
    }


async def validate_draft_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    try:
        progress = await runtime.context.shipment.load_progress(
            UUID(state["conversation_id"]), runtime.context.actor_id
        )
    except AppError as error:
        return _app_error(error, "validate_draft_node")
    if progress.missing_fields:
        result = ShipmentWorkflowResult(
            status="NEEDS_INPUT",
            response="寄件信息发生变化，请补齐后重新报价。",
        )
        return {
            "draft_progress": progress.model_dump(mode="json"),
            "workflow_result": result.model_dump(mode="json"),
        }
    return {
        "draft_progress": progress.model_dump(mode="json"),
        "draft_validated": True,
    }


async def create_quote_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    try:
        quote = await runtime.context.shipment.validate_and_quote(
            UUID(state["conversation_id"]), runtime.context.actor_id
        )
    except AppError as error:
        return _app_error(error, "create_quote_node")
    runtime.context.trace.record(
        "quote.created", quote_version=quote.quote_version, total_cents=quote.total_cents
    )
    return {"quote_progress": quote.model_dump(mode="json")}


async def request_confirmation_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    try:
        snapshot = await runtime.context.shipment.prepare_confirmation(
            UUID(state["conversation_id"]), runtime.context.actor_id
        )
    except AppError as error:
        return _app_error(error, "request_confirmation_node")
    decision_value = interrupt(
        {
            "kind": "shipment_confirmation",
            "draft_revision": snapshot.draft_revision,
            "quote_id": str(snapshot.quote_id),
            "quote_version": snapshot.quote_version,
            "total_cents": snapshot.total_cents,
            "summary": snapshot.summary,
        }
    )
    decision = (
        str(decision_value.get("decision", "defer"))
        if isinstance(decision_value, dict)
        else str(decision_value)
    ).lower()
    if decision == "confirm":
        return {
            "confirmation_snapshot": snapshot.model_dump(mode="json"),
            "confirmation_decision": "confirm",
        }
    if decision == "cancel":
        result = ShipmentWorkflowResult(
            status="CANCELLED", response="已取消本次寄件确认，不会创建运单。"
        )
    else:
        result = ShipmentWorkflowResult(
            status="AWAITING_CONFIRMATION",
            response="已暂缓本次寄件确认，你可以继续咨询其他问题。",
        )
    return {
        "confirmation_snapshot": snapshot.model_dump(mode="json"),
        "confirmation_decision": decision,
        "workflow_result": result.model_dump(mode="json"),
    }


async def create_confirmed_shipment_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    try:
        receipt = await runtime.context.shipment.create_confirmed(
            UUID(state["conversation_id"]),
            runtime.context.actor_id,
            runtime.context.request_id,
        )
    except AppError as error:
        return _app_error(error, "create_confirmed_shipment_node")
    result = ShipmentWorkflowResult(
        status="CREATED",
        response=(
            f"运单 {receipt.shipment_no} 已创建，待支付 "
            f"{receipt.total_cents / 100:.2f} 元。"
        ),
        receipt=receipt,
    )
    runtime.context.trace.record("shipment.created", shipment_no=receipt.shipment_no)
    return {"workflow_result": result.model_dump(mode="json")}


def shipment_failure_node(
    state: ShipmentState,
    runtime: Runtime[AgentRuntimeContext],
) -> ShipmentState:
    error = WorkflowError.model_validate(state["error"])
    runtime.context.trace.record("shipment.failed", code=error.code)
    result = ShipmentWorkflowResult(
        status="FAILED",
        response=error.message,
        error=error,
    )
    return {"workflow_result": result.model_dump(mode="json")}


def draft_action_route(state: ShipmentState) -> str:
    if state.get("error"):
        return "shipment_failure_node"
    if state.get("pending_tool_calls"):
        return "draft_tools_node"
    if state.get("workflow_result"):
        return "__end__"
    return "validate_draft_node"


def draft_tools_route(state: ShipmentState) -> str:
    return "shipment_failure_node" if state.get("error") else "draft_agent_node"


def validation_route(state: ShipmentState) -> str:
    if state.get("error"):
        return "shipment_failure_node"
    if state.get("workflow_result"):
        return "__end__"
    return "create_quote_node"


def quote_route(state: ShipmentState) -> str:
    return "shipment_failure_node" if state.get("error") else "request_confirmation_node"


def confirmation_route(state: ShipmentState) -> str:
    if state.get("error"):
        return "shipment_failure_node"
    if state.get("confirmation_decision") == "confirm":
        return "create_confirmed_shipment_node"
    return "__end__"


def creation_route(state: ShipmentState) -> str:
    return "shipment_failure_node" if state.get("error") else "__end__"


def _model_messages(messages: list[dict[str, object]]) -> list[ModelMessage]:
    result: list[ModelMessage] = []
    for item in messages:
        raw_calls_value = item.get("tool_calls", [])
        raw_calls = raw_calls_value if isinstance(raw_calls_value, list) else []
        calls = tuple(
            ToolCall(
                id=str(raw["id"]),
                name=str(raw["name"]),
                arguments=(
                    dict(raw["arguments"])
                    if isinstance(raw.get("arguments"), dict)
                    else {}
                ),
            )
            for raw in raw_calls
            if isinstance(raw, dict)
        )
        result.append(
            ModelMessage(
                role=str(item.get("role", "user")),
                content=str(item.get("content", "")),
                tool_calls=calls,
                tool_call_id=(
                    str(item["tool_call_id"])
                    if item.get("tool_call_id") is not None
                    else None
                ),
            )
        )
    return result


def _tool_call_dict(call: ToolCall) -> dict[str, object]:
    return {"id": call.id, "name": call.name, "arguments": call.arguments}


def _app_error(error: AppError, source_node: str) -> ShipmentState:
    return _workflow_error(error.code, error.message, source_node)


def _workflow_error(
    code: str,
    message: str,
    source_node: str,
    retryable: bool = False,
) -> ShipmentState:
    error = WorkflowError(
        code=code,
        message=message,
        source_node=source_node,
        retryable=retryable,
    )
    return {"error": error.model_dump(mode="json")}
