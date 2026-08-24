"""Agent Runtime 公开事件和单执行路径测试。"""

from uuid import uuid4

from yitu.agent.runtime.event_mapper import (
    AgentEventMapper,
    AssistantMessageStored,
    NodeCompleted,
    TokenGenerated,
    UserMessageStored,
    WorkflowFailed,
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
