"""在线知识检索端口。"""

from typing import Protocol
from uuid import UUID

from yitu.agent.workflow_state.contracts import KnowledgeEvidence, KnowledgeSearchInput


class KnowledgePort(Protocol):
    async def search(
        self,
        request: KnowledgeSearchInput,
        *,
        actor_id: UUID,
    ) -> KnowledgeEvidence: ...
