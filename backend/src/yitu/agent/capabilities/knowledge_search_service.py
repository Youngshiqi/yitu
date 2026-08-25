"""知识模块只负责检索证据，最终回答仍由助手 Agent 生成。"""

from uuid import UUID

from yitu.agent.tools.base import ToolContext
from yitu.agent.tools.knowledge import (
    KnowledgeSearchInput as ToolKnowledgeSearchInput,
)
from yitu.agent.tools.knowledge import KnowledgeSearchTool
from yitu.agent.workflow.contracts import (
    KnowledgeCitation,
    KnowledgeEvidence,
    KnowledgeSearchInput,
)
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError


class KnowledgeSearchService:
    def __init__(
        self,
        *,
        tool: KnowledgeSearchTool,
        context: ToolContext,
        actor: CurrentUser,
    ) -> None:
        self._tool = tool
        self._context = context
        self._actor = actor

    async def search(
        self,
        request: KnowledgeSearchInput,
        *,
        actor_id: UUID,
    ) -> KnowledgeEvidence:
        self._require_actor(actor_id)
        result = await self._tool.execute(
            ToolKnowledgeSearchInput.model_validate(request.model_dump()),
            self._context,
        )
        citations = [] if result.data is None else result.data.citations
        return KnowledgeEvidence(
            found=result.found,
            citations=[
                KnowledgeCitation.model_validate(item.model_dump())
                for item in citations
            ],
            message=result.message,
        )

    def _require_actor(self, actor_id: UUID) -> None:
        if actor_id != self._actor.id:
            raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能访问本人知识上下文", 403)
