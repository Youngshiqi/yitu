"""冻结前端依赖的 Agent HTTP 与 SSE 公开契约。"""

from datetime import UTC, datetime
from uuid import uuid4

from yitu.agent.schemas import AgentTurnView, MessageView
from yitu.agent.sse import encode_agent_event


def test_agent_sse_contract_keeps_public_delta_shape() -> None:
    assert encode_agent_event("delta", {"content": "你"}) == (
        'event: delta\ndata: {"content": "你"}\n\n'
    )


def test_agent_turn_view_keeps_user_and_assistant_messages() -> None:
    conversation_id = uuid4()
    now = datetime.now(UTC)
    user_view = MessageView(
        id=uuid4(),
        conversation_id=conversation_id,
        role="user",
        content="我要寄件",
        envelope=None,
        created_at=now,
    )
    assistant_view = MessageView(
        id=uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content="请提供收件信息",
        envelope=None,
        created_at=now,
    )

    turn = AgentTurnView(
        user_message=user_view,
        assistant_message=assistant_view,
    )

    assert set(turn.model_dump()) == {"user_message", "assistant_message"}
