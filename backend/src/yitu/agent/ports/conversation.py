"""会话消息持久化端口。"""

from typing import Protocol
from uuid import UUID


class ConversationPort(Protocol):
    async def load_history(
        self, conversation_id: UUID, actor_id: UUID, *, limit: int
    ) -> list[dict[str, object]]: ...

    async def append_message(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        *,
        role: str,
        content: str,
        envelope: dict[str, object] | None = None,
    ) -> dict[str, object]: ...
