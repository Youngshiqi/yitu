"""主助手的单轮 Agent 与白名单工具节点。"""

import json

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yitu.agent.infrastructure.model_adapter import ModelMessage, ToolCall
from yitu.agent.prompts import BUDGET_REFUSAL, SYSTEM_PROMPT
from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.tools.registry import ASSISTANT_TOOL_SPECS
from yitu.agent.workflow.state import (
    AssistantState,
    AssistantToolCall,
    AssistantToolObservation,
    KnowledgeSearchInput,
    WorkflowError,
)


class _StartShipmentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extracted_fields: dict[str, object] = Field(default_factory=dict)


async def assistant_agent_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    result = None
    messages = _model_messages(state.get("messages", []))
    async for event in runtime.context.model.stream_with_tools(
        [ModelMessage(role="system", content=SYSTEM_PROMPT), *messages],
        ASSISTANT_TOOL_SPECS,
    ):
        if event.delta:
            runtime.stream_writer({"type": "token", "content": event.delta})
        if event.result is not None:
            result = event.result
    if result is None:
        return _workflow_error(
            "MODEL_EMPTY_RESULT", "模型没有返回可执行结果", "assistant_agent_node", True
        )

    updated_messages = list(state.get("messages", []))
    assistant_message: dict[str, object] = {
        "role": "assistant",
        "content": result.content or "",
    }
    if result.tool_calls:
        assistant_message["tool_calls"] = [
            _tool_call_dict(call) for call in result.tool_calls
        ]
    updated_messages.append(assistant_message)
    update: AssistantState = {"messages": updated_messages}

    shipment_calls = [
        call for call in result.tool_calls if call.name == "start_shipment"
    ]
    if shipment_calls:
        if len(result.tool_calls) != 1:
            return _workflow_error(
                "MIXED_SHIPMENT_TOOLS",
                "开始寄件不能与其他工具同时执行",
                "assistant_agent_node",
            )
        try:
            args = _StartShipmentArguments.model_validate(shipment_calls[0].arguments)
        except ValidationError:
            return _workflow_error(
                "INVALID_START_SHIPMENT",
                "开始寄件参数无效",
                "assistant_agent_node",
            )
        update["shipment_requested"] = True
        update["shipment_candidate_fields"] = args.extracted_fields
    elif result.tool_calls:
        update["pending_tool_calls"] = [
            _tool_call_dict(call) for call in result.tool_calls
        ]
    else:
        update["response"] = (result.content or "").strip()
    runtime.context.trace.record(
        "assistant.decided", tool_call_count=len(result.tool_calls)
    )
    return update


async def assistant_tools_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    raw_calls = state.get("pending_tool_calls", [])
    if len(raw_calls) > runtime.context.max_tool_calls:
        return _budget_error("assistant_tools_node")
    messages = list(state.get("messages", []))
    try:
        for raw_call in raw_calls:
            call = AssistantToolCall.model_validate(raw_call)
            if call.name == "search_knowledge":
                request = KnowledgeSearchInput.model_validate(call.arguments)
                evidence = await runtime.context.knowledge_search_service.search(
                    request, actor_id=runtime.context.actor_id
                )
                observation = AssistantToolObservation(
                    tool_call_id=call.id,
                    name=call.name,
                    found=evidence.found,
                    content=evidence.message,
                    data=evidence.model_dump(mode="json"),
                )
            else:
                observation = await runtime.context.assistant_read_service.execute(
                    call, actor_id=runtime.context.actor_id
                )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        observation.model_dump(mode="json"), ensure_ascii=False
                    ),
                    "tool_call_id": call.id,
                }
            )
            runtime.context.trace.record("tool.completed", tool=call.name)
    except ValidationError:
        return _workflow_error(
            "AGENT_TOOL_ARGUMENT_INVALID",
            "模型请求了无效或未授权的工具参数",
            "assistant_tools_node",
        )

    # 工具执行完毕后，调用 LLM 基于工具结果生成最终回复（不再回边）
    model_messages = _model_messages(messages)
    response_parts: list[str] = []
    async for chunk in runtime.context.model.stream(
        [ModelMessage(role="system", content=SYSTEM_PROMPT), *model_messages]
    ):
        if chunk:
            runtime.stream_writer({"type": "token", "content": chunk})
            response_parts.append(chunk)
    response = "".join(response_parts).strip()
    if not response:
        response = "抱歉，我暂时无法完成这次请求。"
    messages.append({"role": "assistant", "content": response})

    return {
        "messages": messages,
        "pending_tool_calls": [],
        "response": response,
    }


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


def _budget_error(source_node: str) -> AssistantState:
    return _workflow_error("AGENT_BUDGET_EXCEEDED", BUDGET_REFUSAL, source_node)


def _workflow_error(
    code: str,
    message: str,
    source_node: str,
    retryable: bool = False,
) -> AssistantState:
    error = WorkflowError(
        code=code,
        message=message,
        source_node=source_node,
        retryable=retryable,
    )
    return {"error": error.model_dump(mode="json")}
