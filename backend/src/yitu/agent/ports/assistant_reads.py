"""主助手白名单只读工具端口。"""

from typing import Protocol
from uuid import UUID

from yitu.agent.workflow_state.contracts import (
    AssistantToolCall,
    AssistantToolObservation,
)


class AssistantReadPort(Protocol):
    async def execute(
        self,
        call: AssistantToolCall,
        *,
        actor_id: UUID,
    ) -> AssistantToolObservation: ...
