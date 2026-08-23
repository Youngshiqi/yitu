"""草稿填写 agentic loop：模型通过 update_draft 工具增量填字段 + 主动追问。"""

import asyncio
from typing import Any, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.agent.model_adapter import (
    ModelAdapter,
    ModelMessage,
    ToolCall,
    ToolCallResult,
)
from yitu.agent.nodes import _budget_refusal
from yitu.agent.prompts import DRAFT_LOOP_PROMPT
from yitu.agent.state import AgentState
from yitu.agent.tools.drafts import (
    UPDATE_DRAFT_TOOL_SPECS,
    execute_save_address,
    execute_update_draft,
)
from yitu.identity.service import CurrentUser


def build_draft_loop_graph(
    model: ModelAdapter,
    *,
    actor: CurrentUser,
    session: AsyncSession,
    addresses: list[Address],
    checkpointer: Any = None,
    stream_queue: asyncio.Queue[str | None] | None = None,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """构建草稿填写子图：draft_agent ⇄ draft_tools 循环，无工具调用时结束。

    stream_queue 非 None 时，draft_agent 节点用 stream_with_tools 流式输出
    内容增量到队列，供外层 SSE 转发；为 None 时退回 complete_with_tools。
    """
    graph = StateGraph(AgentState)
    graph.add_node("draft_agent", draft_agent_node(model, stream_queue))
    graph.add_node("draft_tools", draft_tools_node(session, actor, addresses))
    graph.add_edge(START, "draft_agent")
    graph.add_conditional_edges(
        "draft_agent",
        route_after_draft_agent,
        {"draft_tools": "draft_tools", END: END},
    )
    graph.add_edge("draft_tools", "draft_agent")
    return graph.compile(checkpointer=checkpointer)


def draft_agent_node(
    model: ModelAdapter,
    stream_queue: asyncio.Queue[str | None] | None = None,
) -> Any:
    """让模型决定：调用 update_draft 填字段，或返回纯文本（追问/完成）。

    stream_queue 非 None 时用流式接口，内容增量即时推入队列。
    """

    async def _agent(state: AgentState) -> AgentState:
        refusal = _budget_refusal(state)
        if refusal is not None:
            if stream_queue is not None:
                await stream_queue.put(refusal)
            return {"draft_response": refusal}
        turns = list(state.get("draft_turns", []))
        messages = _turns_to_messages(turns) if turns else _initial_messages(state)

        if stream_queue is not None:
            result: ToolCallResult | None = None
            async for event in model.stream_with_tools(messages, UPDATE_DRAFT_TOOL_SPECS):
                if event.delta:
                    await stream_queue.put(event.delta)
                if event.result is not None:
                    result = event.result
            if result is None:
                result = ToolCallResult(content=None, tool_calls=())
        else:
            result = await model.complete_with_tools(messages, UPDATE_DRAFT_TOOL_SPECS)

        assistant: dict[str, object] = {
            "role": "assistant",
            "content": result.content or "",
        }
        if result.tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in result.tool_calls
            ]
        update: AgentState = {"draft_turns": [assistant]}
        if result.tool_calls:
            update["tool_call_count"] = state.get("tool_call_count", 0) + 1
        else:
            update["draft_response"] = result.content or ""
        return update

    return _agent


def draft_tools_node(
    session: AsyncSession,
    actor: CurrentUser,
    addresses: list[Address],
) -> Any:
    """执行最后一条助手消息里的工具调用，结果作为 tool 消息回填。"""

    async def _tools(state: AgentState) -> AgentState:
        turns = list(state.get("draft_turns", []))
        if not turns:
            return {}
        calls = _as_call_list(turns[-1].get("tool_calls"))
        conversation_id = UUID(str(state["conversation_id"]))
        results: list[dict[str, object]] = []
        for call in calls:
            name = call.get("name")
            arguments = call.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            if name == "update_draft":
                content = await execute_update_draft(
                    session, actor, addresses, conversation_id, arguments
                )
            elif name == "save_address":
                content = await execute_save_address(
                    session, actor, conversation_id, arguments
                )
            else:
                content = f"未知工具：{name}"
            results.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": call.get("id"),
                }
            )
        return {"draft_turns": results}

    return _tools


def route_after_draft_agent(state: AgentState) -> str:
    """最后一条助手消息带工具调用则继续执行工具，否则结束 loop。"""
    turns = state.get("draft_turns", [])
    if not turns:
        return END
    return "draft_tools" if turns[-1].get("tool_calls") else END


def _initial_messages(state: AgentState) -> list[ModelMessage]:
    """首轮消息：草稿 loop 指令 + 最近历史 + 当前用户消息。"""
    missing = state.get("draft_missing_fields", [])
    labels = state.get("address_labels", [])
    filled = state.get("draft_filled_fields", "")
    system = DRAFT_LOOP_PROMPT.format(
        filled_fields=filled or "（无）",
        missing_fields="、".join(missing) if missing else "（无）",
        address_labels="、".join(labels) if labels else "（无）",
    )
    messages = [ModelMessage(role="system", content=system)]
    # 只取 10 条
    for item in state.get("history", [])[-10:]:
        messages.append(
            ModelMessage(
                role=str(item.get("role", "user")),
                content=str(item.get("content", "")),
            )
        )
    messages.append(
        ModelMessage(role="user", content=str(state.get("user_message", "")))
    )
    return messages


def _turns_to_messages(turns: list[dict[str, object]]) -> list[ModelMessage]:
    """把草稿 loop 的自研 dict 消息流转换为模型消息。"""
    messages: list[ModelMessage] = []
    for turn in turns:
        tool_calls = tuple(
            ToolCall(
                id=str(call["id"]),
                name=str(call["name"]),
                arguments=_as_arguments(call.get("arguments")),
            )
            for call in _as_call_list(turn.get("tool_calls"))
        )
        tool_call_id = turn.get("tool_call_id")
        messages.append(
            ModelMessage(
                role=str(turn.get("role", "assistant")),
                content=str(turn.get("content", "")),
                tool_calls=tool_calls,
                tool_call_id=str(tool_call_id)
                if tool_call_id is not None
                else None,
            )
        )
    return messages


def _as_call_list(value: object) -> list[dict[str, object]]:
    """把状态里弱类型化的工具调用还原为已知结构，防御异常输入。"""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in value if isinstance(item, dict)]


def _as_arguments(value: object) -> dict[str, object]:
    """把弱类型化的工具参数还原为 dict，非 dict 时退回空对象。"""
    return cast(dict[str, object], value) if isinstance(value, dict) else {}
