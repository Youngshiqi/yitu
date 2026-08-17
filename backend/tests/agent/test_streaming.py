"""生成阶段流式输出契约：stream_with_tools、工具回复流式、草稿 loop 流式转发。"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from yitu.agent.model_adapter import (
    FixedModelAdapter,
    ModelMessage,
    StructuredT,
    ToolCall,
    ToolCallResult,
    ToolStreamEvent,
)
from yitu.agent.draft_loop import build_draft_loop_graph
from yitu.agent.service import AgentConversationService
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser

pytestmark = pytest.mark.asyncio


# ---------- stream_with_tools ----------


async def test_fixed_adapter_stream_with_tools_yields_single_delta_and_result() -> None:
    adapter = FixedModelAdapter()
    events = [
        event
        async for event in adapter.stream_with_tools(
            [ModelMessage(role="user", content="你好")], []
        )
    ]
    # FixedModelAdapter 的 complete_with_tools 返回空工具调用，
    # content=None → 无 delta，仅最终 result 事件。
    assert len(events) == 1
    assert events[0].delta == ""
    assert events[0].result is not None
    assert events[0].result.tool_calls == ()


def _actor() -> CurrentUser:
    return CurrentUser(uuid4(), Role.CUSTOMER, None)


# ---------- 流式草稿 loop ----------


class StreamingLoopModel:
    """模拟流式模型：第一轮回放工具调用，第二轮流式返回最终文本。"""

    def __init__(self) -> None:
        self.round = 0
        self.stream_with_tools_calls = 0

    async def complete_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> ToolCallResult:
        raise AssertionError("流式模式下不应调用 complete_with_tools")

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        raise AssertionError("草稿 loop 不应走纯文本 complete")

    async def complete_structured(
        self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
    ) -> StructuredT:
        raise AssertionError("草稿 loop 不应走结构化理解")

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        raise AssertionError("草稿 loop 不应走无工具流式")
        yield ""

    async def stream_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> AsyncIterator[ToolStreamEvent]:
        self.stream_with_tools_calls += 1
        if self.round == 0:
            # 第一轮：流式返回少量内容 + 工具调用
            yield ToolStreamEvent(delta="好的，")
            yield ToolStreamEvent(delta="我来更新地址。")
            self.round += 1
            yield ToolStreamEvent(
                result=ToolCallResult(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id="call-1",
                            name="update_draft",
                            arguments={"sender_address_label": "公司"},
                        ),
                    ),
                )
            )
        else:
            # 第二轮：流式返回最终文本，无工具调用
            yield ToolStreamEvent(delta="收件地址已设置。")
            yield ToolStreamEvent(delta="请告诉我包裹重量。")
            yield ToolStreamEvent(
                result=ToolCallResult(
                    content="收件地址已设置。请告诉我包裹重量。",
                    tool_calls=(),
                )
            )


async def test_draft_loop_streams_deltas_via_queue() -> None:
    """stream_queue 传递时 draft_agent 应走 stream_with_tools 并推送增量。"""
    model = StreamingLoopModel()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    graph = build_draft_loop_graph(
        model,
        actor=_actor(),
        session=SimpleNamespace(),  # type: ignore[arg-type]
        addresses=[],
        stream_queue=queue,
    )
    state: dict[str, Any] = {
        "conversation_id": str(uuid4()),
        "user_id": str(uuid4()),
        "user_message": "从公司寄到上海",
        "history": [],
        "draft_missing_fields": ["sender_address_id"],
        "address_labels": ["公司"],
        "turn_count": 0,
        "tool_call_count": 0,
        "max_turns": 8,
        "max_tool_calls": 4,
    }

    # 工具执行节点会调用 execute_update_draft，这里直接跳过图执行验证节点级流式。
    from yitu.agent.draft_loop import draft_agent_node

    node = draft_agent_node(model, stream_queue=queue)
    update = await node(state)
    assert update["draft_turns"][0]["tool_calls"] is not None

    # 从队列取出已推送的 delta
    deltas: list[str] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            deltas.append(item)
    assert "好的，" in deltas
    assert "我来更新地址。" in deltas
    assert model.stream_with_tools_calls == 1


async def test_draft_loop_without_queue_uses_complete_with_tools() -> None:
    """stream_queue 为 None 时退回 complete_with_tools，行为不变。"""

    class NonStreamingModel:
        def __init__(self) -> None:
            self.complete_with_tools_calls = 0

        async def complete_with_tools(
            self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
        ) -> ToolCallResult:
            self.complete_with_tools_calls += 1
            return ToolCallResult(content="请补充重量。", tool_calls=())

        async def complete(self, messages: Sequence[ModelMessage]) -> str:
            raise AssertionError("不应调用")

        async def complete_structured(
            self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
        ) -> StructuredT:
            raise AssertionError("不应调用")

        async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
            raise AssertionError("不应调用")
            yield ""

        async def stream_with_tools(
            self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
        ) -> AsyncIterator[ToolStreamEvent]:
            raise AssertionError("无队列时不应调用流式工具接口")
            yield ToolStreamEvent()

    model = NonStreamingModel()
    from yitu.agent.draft_loop import draft_agent_node

    node = draft_agent_node(model, stream_queue=None)
    state: dict[str, Any] = {
        "conversation_id": str(uuid4()),
        "user_id": str(uuid4()),
        "user_message": "从公司寄",
        "history": [],
        "draft_missing_fields": [],
        "address_labels": [],
    }
    update = await node(state)
    assert update["draft_response"] == "请补充重量。"
    assert model.complete_with_tools_calls == 1


# ---------- _stream_tool_reply 流式 ----------


class ChunkedStreamModel:
    """stream 方法按块返回文本，验证回复按块 yield。"""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.stream_calls = 0

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        raise AssertionError("流式回复不应走 complete")

    async def complete_structured(
        self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
    ) -> StructuredT:
        raise AssertionError("不应调用")

    async def complete_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> ToolCallResult:
        raise AssertionError("不应调用")

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        self.stream_calls += 1
        for chunk in self._chunks:
            yield chunk

    async def stream_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> AsyncIterator[ToolStreamEvent]:
        raise AssertionError("不应调用")
        yield ToolStreamEvent()


async def test_stream_tool_reply_yields_chunks() -> None:
    from yitu.agent.tools.base import ToolResult
    from pydantic import BaseModel

    class FakeData(BaseModel):
        value: str = "test"

    model = ChunkedStreamModel(["运单", "已揽收", "。"])
    service = AgentConversationService(session=SimpleNamespace())  # type: ignore[arg-type]
    tool_result = ToolResult(tool="shipment_read", found=True, data=FakeData(), message="ok")

    chunks = [
        chunk async for chunk in service._stream_tool_reply(model, [], [], tool_result)
    ]
    assert chunks == ["运单", "已揽收", "。"]
    assert model.stream_calls == 1
