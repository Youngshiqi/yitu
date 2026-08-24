"""Agent Runtime 公开事件和单执行路径测试。"""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from tests.agent.fakes import ScriptedModelPort
from tests.agent.test_assistant_graph import _context, _empty_shipment_graph
from yitu.agent.model_adapter import ToolCallResult
from yitu.agent.runtime.event_mapper import (
    AgentEventMapper,
    AssistantMessageStored,
    NodeCompleted,
    TokenGenerated,
    UserMessageStored,
    WorkflowFailed,
)
from yitu.agent.runtime.runtime import AgentRuntime
from yitu.agent.workflows.assistant_graph import build_assistant_graph


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


async def test_runtime_streams_real_graph_through_one_public_event_path() -> None:
    model = ScriptedModelPort(
        [ToolCallResult(content="可以，我来帮你。", tool_calls=())]
    )
    context = _context(model)
    runtime = AgentRuntime(
        build_assistant_graph(_empty_shipment_graph(), checkpointer=MemorySaver())
    )

    events = [
        event
        async for event in runtime.stream_message(uuid4(), "你好", context)
    ]

    assert [name for name, _ in events] == ["user_message", "delta", "done"]
    assert events[1] == ("delta", {"content": "可以，我来帮你。"})
