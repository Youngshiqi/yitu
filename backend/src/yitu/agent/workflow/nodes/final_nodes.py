"""子图交接、成功持久化和显式失败节点。"""

from uuid import UUID

from langgraph.runtime import Runtime

from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.workflow.state import (
    AssistantState,
    WorkflowError,
)


# 负责把助手回复写入数据库
async def finalize_turn_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    response = state.get("response", "").strip()
    if not response:
        response = "抱歉，我暂时无法完成这次请求。"
    await runtime.context.conversation_service.append_message(
        UUID(state["conversation_id"]),
        runtime.context.actor_id,
        role="assistant",
        content=response,
        envelope={"trace": runtime.context.trace.summary()},
    )
    runtime.context.trace.record("turn.finalized")
    return {"response": response}


# 负责把主图 WorkflowError 写入数据库
async def handle_failure_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    error = WorkflowError.model_validate(state["error"])
    await runtime.context.conversation_service.append_message(
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
