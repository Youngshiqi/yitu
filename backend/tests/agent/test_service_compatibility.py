"""service.py 只转发 Runtime 公开事件，不再拥有编排分支。"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from yitu.agent.service import AgentConversationService


class FakeRuntime:
    async def stream_message(
        self, conversation_id: Any, content: str, context: Any
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        del conversation_id, content, context
        yield "user_message", {"role": "user"}
        yield "delta", {"content": "完成"}
        yield "done", {"role": "assistant"}


async def test_service_stream_forwards_runtime_public_events() -> None:
    service = AgentConversationService(
        object(),  # type: ignore[arg-type]
        runtime=FakeRuntime(),  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in service.stream_message(
            uuid4(), "寄件", object()  # type: ignore[arg-type]
        )
    ]

    assert events == [
        ("user_message", {"role": "user"}),
        ("delta", {"content": "完成"}),
        ("done", {"role": "assistant"}),
    ]
