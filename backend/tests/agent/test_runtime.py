"""Agent Graph Runner 公开事件和单执行路径测试。"""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from tests.agent.fakes import FakeShipmentConversationService, ScriptedModel
from tests.agent.test_assistant_graph import _context
from yitu.agent.model_adapter import ToolCall, ToolCallResult
from yitu.agent.runtime.event_mapper import (
    AgentEventMapper,
    AssistantMessageStored,
    NodeCompleted,
    TokenGenerated,
    UserMessageStored,
    WorkflowFailed,
)
from yitu.agent.runtime.graph_runner import AgentGraphRunner
from yitu.agent.workflow.assistant_graph import build_assistant_graph
from yitu.agent.workflow.state import (
    ConfirmationSnapshot,
    DraftProgress,
    QuoteProgress,
    ShipmentReceipt,
)


def test_internal_token_maps_to_existing_delta_contract() -> None:
    mapper = AgentEventMapper()

    assert mapper.map(TokenGenerated(content="驿")) == (
        "delta",
        {"content": "驿"},
    )


def test_only_public_lifecycle_events_are_exposed() -> None:
    mapper = AgentEventMapper()
    user_payload = {"id": str(uuid4()), "role": "user"}
    assistant_payload = {"id": str(uuid4()), "role": "assistant"}

    assert mapper.map(UserMessageStored(payload=user_payload)) == (
        "user_message",
        user_payload,
    )
    assert mapper.map(AssistantMessageStored(payload=assistant_payload)) == (
        "done",
        assistant_payload,
    )
    assert mapper.map(WorkflowFailed(code="FAILED", message="失败")) == (
        "error",
        {"code": "FAILED", "message": "失败"},
    )
    assert mapper.map(NodeCompleted(node="assistant_tools_node")) is None


async def test_graph_runner_streams_real_graph_through_one_public_event_path() -> None:
    model = ScriptedModel([ToolCallResult(content="可以，我来帮你。", tool_calls=())])
    context = _context(model)
    runner = AgentGraphRunner(build_assistant_graph(checkpointer=MemorySaver()))

    events = [event async for event in runner.stream_message(uuid4(), "你好", context)]

    assert [name for name, _ in events] == ["user_message", "delta", "done"]
    assert events[1] == ("delta", {"content": "可以，我来帮你。"})


async def test_graph_runner_exposes_confirmation_then_resumes_same_thread() -> None:
    conversation_id = uuid4()
    quote_id = uuid4()
    model = ScriptedModel(
        [
            ToolCallResult(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="handoff",
                        name="start_shipment",
                        arguments={"extracted_fields": {}},
                    ),
                ),
            ),
        ]
    )
    shipment = FakeShipmentConversationService(
        DraftProgress(status="READY_FOR_QUOTE", revision=1, missing_fields=[]),
        quote=QuoteProgress(
            quote_id=quote_id, quote_version="v1", draft_revision=1, total_cents=1200
        ),
        confirmation=ConfirmationSnapshot(
            conversation_id=conversation_id,
            draft_revision=1,
            quote_id=quote_id,
            quote_version="v1",
            total_cents=1200,
            summary="文件",
        ),
        receipt=ShipmentReceipt(
            shipment_id=uuid4(), shipment_no="YT202608240003", total_cents=1200
        ),
    )
    context = _context(model)
    object.__setattr__(context, "shipment_conversation_service", shipment)
    runner = AgentGraphRunner(build_assistant_graph(checkpointer=MemorySaver()))

    first = [
        event
        async for event in runner.stream_message(conversation_id, "寄文件", context)
    ]
    second = [
        event async for event in runner.stream_message(conversation_id, "确认", context)
    ]

    assert first[-1][0] == "done"
    assert second[-1][0] == "done"
    assert shipment.create_requests == ["request-1"]
