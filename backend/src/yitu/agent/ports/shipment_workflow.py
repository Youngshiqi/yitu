"""寄件子图使用的确定性业务端口。"""

from typing import Protocol
from uuid import UUID

from yitu.agent.workflow_state.contracts import (
    ConfirmationSnapshot,
    DraftProgress,
    DraftToolCall,
    QuoteProgress,
    ShipmentReceipt,
)


class ShipmentWorkflowPort(Protocol):
    async def load_progress(
        self, conversation_id: UUID, actor_id: UUID
    ) -> DraftProgress: ...

    async def execute_draft_tool(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        call: DraftToolCall,
    ) -> DraftProgress: ...

    async def validate_and_quote(
        self, conversation_id: UUID, actor_id: UUID
    ) -> QuoteProgress: ...

    async def prepare_confirmation(
        self, conversation_id: UUID, actor_id: UUID
    ) -> ConfirmationSnapshot: ...

    async def create_confirmed(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        request_id: str,
    ) -> ShipmentReceipt: ...
