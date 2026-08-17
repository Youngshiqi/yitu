"""草稿填写 agentic loop 的循环结构、预算护栏与 update_draft 工具契约。"""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from time import monotonic
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from langgraph.checkpoint.memory import MemorySaver

from yitu.agent.draft_loop import build_draft_loop_graph
from yitu.agent.drafts import DraftPatch, DraftView
from yitu.agent.model_adapter import (
    ModelMessage,
    StructuredT,
    ToolCall,
    ToolCallResult,
)
from yitu.agent.prompts import BUDGET_REFUSAL
from yitu.agent.service import _clear_thread
from yitu.agent.state import AgentState
from yitu.agent.tools.drafts import _match_address_label, execute_update_draft
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser

TZ = ZoneInfo("Asia/Shanghai")


class LoopModel:
    """按队列回放 complete_with_tools，队列耗尽后回退为纯文本追问。"""

    def __init__(
        self,
        responses: list[ToolCallResult],
        *,
        fallback: str = "请补充缺失字段。",
    ) -> None:
        self._responses = iter(responses)
        self._fallback = fallback
        self.calls = 0

    async def complete_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> ToolCallResult:
        del messages, tools
        self.calls += 1
        try:
            return next(self._responses)
        except StopIteration:
            return ToolCallResult(content=self._fallback, tool_calls=())

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        del messages
        raise AssertionError("草稿 loop 不应走纯文本 complete")

    async def complete_structured(
        self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
    ) -> StructuredT:
        del messages, response_model
        raise AssertionError("草稿 loop 不应走结构化理解")

    def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        del messages
        raise AssertionError("草稿 loop 不应流式输出")


def _actor() -> CurrentUser:
    return CurrentUser(uuid4(), Role.CUSTOMER, None)


def _build_graph(model: LoopModel, addresses: list[Any] | None = None) -> Any:
    return build_draft_loop_graph(
        model,
        actor=_actor(),
        session=SimpleNamespace(),  # type: ignore[arg-type]
        addresses=addresses if addresses is not None else [],
    )


def _loop_state(**overrides: Any) -> AgentState:
    state: dict[str, Any] = {
        "conversation_id": str(uuid4()),
        "user_id": str(uuid4()),
        "user_message": "从公司寄，重 2.5 公斤",
        "history": [],
        "draft_missing_fields": ["sender_address_id", "estimated_weight_grams"],
        "address_labels": ["公司", "家里"],
        "turn_count": 0,
        "tool_call_count": 0,
        "max_turns": 8,
        "max_tool_calls": 4,
        "execution_started_at": monotonic(),
        "timeout_seconds": 30.0,
    }
    state.update(overrides)
    return cast(AgentState, state)


@pytest.mark.asyncio
async def test_draft_loop_ends_without_tool_calls() -> None:
    model = LoopModel([], fallback="请问寄件地址是哪个？")
    graph = _build_graph(model)

    result = await graph.ainvoke(_loop_state())

    assert result["draft_response"] == "请问寄件地址是哪个？"
    assert len(result["draft_turns"]) == 1
    assert model.calls == 1


@pytest.mark.asyncio
async def test_draft_loop_runs_tool_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execute(
        session: object,
        actor: CurrentUser,
        addresses: list[Any],
        conversation_id: UUID,
        arguments: dict[str, object],
    ) -> str:
        del session, actor, addresses, conversation_id
        assert arguments == {"estimated_weight_grams": 2500}
        return "已更新草稿字段。"

    monkeypatch.setattr("yitu.agent.draft_loop.execute_update_draft", fake_execute)

    model = LoopModel(
        [
            ToolCallResult(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_1",
                        name="update_draft",
                        arguments={"estimated_weight_grams": 2500},
                    ),
                ),
            ),
            ToolCallResult(
                content="寄件信息已更新，还需要补充收件地址。",
                tool_calls=(),
            ),
        ]
    )
    graph = _build_graph(model)

    result = await graph.ainvoke(_loop_state())

    assert result["draft_response"] == "寄件信息已更新，还需要补充收件地址。"
    turns = result["draft_turns"]
    assert len(turns) == 3
    assert turns[0]["role"] == "assistant" and turns[0].get("tool_calls")
    assert turns[1]["role"] == "tool"
    assert turns[2]["role"] == "assistant" and not turns[2].get("tool_calls")
    assert model.calls == 2


@pytest.mark.asyncio
async def test_draft_loop_budget_refusal_stops_before_model() -> None:
    model = LoopModel([])
    graph = _build_graph(model)

    result = await graph.ainvoke(_loop_state(tool_call_count=4, max_tool_calls=4))

    assert result["draft_response"] == BUDGET_REFUSAL
    assert model.calls == 0


def test_match_address_label_requires_unique_match() -> None:
    company_a: Any = SimpleNamespace(id=uuid4(), label="公司", district_code="110101")
    home: Any = SimpleNamespace(id=uuid4(), label="家里", district_code="310101")
    addresses: list[Any] = [company_a, home]

    matched: Any = _match_address_label("公司", addresses)
    assert matched is company_a
    assert _match_address_label("不存在", addresses) is None

    company_b: Any = SimpleNamespace(id=uuid4(), label="公司", district_code="440101")
    assert _match_address_label("公司", [company_a, company_b]) is None


@pytest.mark.asyncio
async def test_update_draft_resolves_unique_label_and_rejects_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    conversation_id = uuid4()
    unique: Any = SimpleNamespace(id=uuid4(), label="公司", district_code="110101")
    updated: list[DraftPatch] = []

    def _draft_view(missing: list[str]) -> DraftView:
        return DraftView(
            id=uuid4(),
            conversation_id=conversation_id,
            payload={},
            revision=1,
            status="INCOMPLETE" if missing else "READY_FOR_QUOTE",
            missing_fields=missing,
            quote_id=None,
            quote_version=None,
            updated_at=datetime(2026, 8, 17, tzinfo=TZ),
        )

    class FakeDraftService:
        def __init__(self, session: object) -> None:
            del session

        async def update(
            self, cid: UUID, a: CurrentUser, patch: DraftPatch
        ) -> DraftView:
            del cid, a
            updated.append(patch)
            return _draft_view(["receiver_address_id"])

        async def get_or_create(self, cid: UUID, a: CurrentUser) -> DraftView:
            del cid, a
            return _draft_view(["sender_address_id"])

    monkeypatch.setattr("yitu.agent.tools.drafts.DraftService", FakeDraftService)

    # 唯一标签 → 解析为地址 ID 后落库。
    result = await execute_update_draft(
        SimpleNamespace(),  # type: ignore[arg-type]
        actor,
        [unique],
        conversation_id,
        {"sender_address_label": "公司"},
    )
    assert len(updated) == 1
    assert updated[0].sender_address_id == unique.id
    assert "仍缺失字段" in result

    # 多义标签 → 不落库，返回未匹配提示。
    updated.clear()
    ambiguous: list[Any] = [
        unique,
        SimpleNamespace(id=uuid4(), label="公司", district_code="440101"),
    ]
    result = await execute_update_draft(
        SimpleNamespace(),  # type: ignore[arg-type]
        actor,
        ambiguous,
        conversation_id,
        {"sender_address_label": "公司"},
    )
    assert len(updated) == 0
    assert "未匹配地址" in result


@pytest.mark.asyncio
async def test_draft_loop_clears_thread_between_turns() -> None:
    model = LoopModel([], fallback="请补充收件地址。")
    saver = MemorySaver()
    graph = build_draft_loop_graph(
        model,
        actor=_actor(),
        session=SimpleNamespace(),  # type: ignore[arg-type]
        addresses=[],
        checkpointer=saver,
    )
    thread_id = str(uuid4())
    config: Any = {"configurable": {"thread_id": thread_id}}

    first = await graph.ainvoke(_loop_state(conversation_id=thread_id), config=config)
    assert len(first["draft_turns"]) == 1

    # service 每轮先清空 thread，第二轮不累积上一轮的 assistant 消息。
    await _clear_thread(saver, thread_id)
    second = await graph.ainvoke(_loop_state(conversation_id=thread_id), config=config)
    assert len(second["draft_turns"]) == 1

    # 对照：不清空时 add reducer 会跨请求累积，证明 _clear_thread 确有拦截作用。
    third = await graph.ainvoke(_loop_state(conversation_id=thread_id), config=config)
    assert len(third["draft_turns"]) == 2
