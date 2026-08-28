"""主图上下文加载与确定性安全守卫。"""

import re
from uuid import UUID

from langgraph.runtime import Runtime

from yitu.agent.prompts import CROSS_USER_REFUSAL, INJECTION_REFUSAL
from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.workflow.state import AssistantState, WorkflowError

_INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则|提示词)"),
    re.compile(
        r"(显示|泄露|输出|show|reveal|print).{0,16}(系统提示词|system prompt)",
        re.IGNORECASE,
    ),
    re.compile(r"(绕过|取消|禁用).{0,8}(权限|安全|授权|审核)"),
    re.compile(r"you are now|developer message", re.IGNORECASE),
)
_CROSS_USER_PATTERNS = (
    re.compile(r"(其他|别人|别人的|任意|全部)(客户|用户)?.{0,8}运单"),
    re.compile(r"查询.{0,8}(其他|别人|任意)(客户|用户)"),
)


async def load_context_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    conversation_id = UUID(state["conversation_id"])
    history = await runtime.context.conversation_service.load_history(
        conversation_id,
        runtime.context.actor_id,
        limit=runtime.context.history_limit,
    )
    user_message = state["user_message"].strip()
    messages = [
        {
            "role": str(item.get("role", "user")),
            "content": str(item.get("content", "")),
            **({"tool_calls": item["tool_calls"]} if "tool_calls" in item else {}),
            **(
                {"tool_call_id": item["tool_call_id"]} if "tool_call_id" in item else {}
            ),
        }
        for item in history
    ]
    if (
        not messages
        or messages[-1].get("role") != "user"
        or messages[-1].get("content") != user_message
    ):
        messages.append({"role": "user", "content": user_message})
    runtime.context.trace.record("context.loaded", message_count=len(messages))
    # 同一 thread 的 checkpoint 会跨回合保留 State；本轮入口必须清掉上轮
    # 的路由标记和交易中间数据，不能因为陈旧值再次进入寄件或建单节点。
    return {
        "messages": messages,
        "pending_tool_calls": [],
        "shipment_requested": False,
        "shipment_candidate_fields": {},
        "shipment_progress": {},
        "quote_progress": {},
        "confirmation_snapshot": {},
        "response": "",
        "error": {},
    }


def security_gate_node(
    state: AssistantState,
    runtime: Runtime[AgentRuntimeContext],
) -> AssistantState:
    message = state["user_message"].strip()
    if any(pattern.search(message) for pattern in _INJECTION_PATTERNS):
        error = WorkflowError(
            code="PROMPT_INJECTION_BLOCKED",
            message=INJECTION_REFUSAL,
            source_node="security_gate_node",
        )
    elif any(pattern.search(message) for pattern in _CROSS_USER_PATTERNS):
        error = WorkflowError(
            code="CROSS_USER_ACCESS_BLOCKED",
            message=CROSS_USER_REFUSAL,
            source_node="security_gate_node",
        )
    else:
        runtime.context.trace.record("security.allowed")
        return {}
    runtime.context.trace.record("security.blocked", code=error.code)
    return {"error": error.model_dump(mode="json")}
