"""子图交接、成功持久化和显式失败节点。"""

from typing import Any
from uuid import UUID

from langgraph.runtime import Runtime

from yitu.agent.runtime.context import AgentRuntimeContext
from yitu.agent.workflow_state import (
    AssistantState,
    ShipmentState,
    ShipmentWorkflowResult,
    WorkflowError,
)


async def shipment_workflow_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
    *,
    shipment_graph: Any,
) -> AssistantState:
    child_input: ShipmentState = {
        "conversation_id": state["conversation_id"],
        "handoff": state["shipment_handoff"],
    }
    # 子图不覆盖 config/context/checkpointer，父线程的 checkpoint namespace 会自动传播。
    child_result = await shipment_graph.ainvoke(child_input)
    raw_result = child_result.get("workflow_result")
    if not isinstance(raw_result, dict):
        error = WorkflowError(
            code="SHIPMENT_WORKFLOW_INCOMPLETE",
            message="寄件工作流未返回结果",
            source_node="shipment_workflow_node",
            retryable=True,
        )
        return {"error": error.model_dump(mode="json")}
    result = ShipmentWorkflowResult.model_validate(raw_result)
    runtime.context.trace.record("shipment.completed", status=result.status)
    return {
        "shipment_result": result.model_dump(mode="json"),
        "response": result.response,
    }


async def finalize_turn_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    response = state.get("response", "").strip()
    if not response:
        response = "抱歉，我暂时无法完成这次请求。"
    await runtime.context.conversation.append_message(
        UUID(state["conversation_id"]),
        runtime.context.actor_id,
        role="assistant",
        content=response,
        envelope={"trace": runtime.context.trace.summary()},
    )
    runtime.context.trace.record("turn.finalized")
    return {"response": response}


async def handle_failure_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    error = WorkflowError.model_validate(state["error"])
    await runtime.context.conversation.append_message(
        UUID(state["conversation_id"]),
        runtime.context.actor_id,
        role="assistant",
        content=error.message,
        envelope={
            "workflow_error": error.model_dump(mode="json"),
            "trace": runtime.context.trace.summary(),
        },
    )
    runtime.context.trace.record("turn.failed", code=error.code)
    return {"response": error.message}


def shipment_result_route(state: AssistantState) -> str:
    return "handle_failure_node" if state.get("error") else "finalize_turn_node"
