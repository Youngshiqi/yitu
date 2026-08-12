"""已发布知识库的 RAG 检索工具。"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.knowledge.retrieval import KnowledgeRetriever


class KnowledgeSearchInput(BaseModel):
    """知识检索的严格输入，限制候选输出规模。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    category: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=5, ge=1, le=5)


class KnowledgeCitation(BaseModel):
    """回答可验证所需的知识证据字段。"""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    filename: str
    index_version: int
    title: str | None
    page_start: int | None
    page_end: int | None
    content: str
    score: float


class KnowledgeSearchResult(BaseModel):
    """已发布知识证据集合。"""

    model_config = ConfigDict(extra="forbid")

    citations: list[KnowledgeCitation]


class KnowledgeSearchTool:
    """调用生产混合检索器，只返回已发布且生效的知识证据。"""

    async def execute(
        self,
        request: KnowledgeSearchInput,
        context: ToolContext,
    ) -> ToolResult[KnowledgeSearchResult]:
        evidence = await KnowledgeRetriever(context.session).search(
            request.query,
            category=request.category,
            limit=request.limit,
        )
        citations = [
            KnowledgeCitation(
                document_id=item.document_id,
                filename=item.filename,
                index_version=item.index_version,
                title=item.title,
                page_start=item.page_start,
                page_end=item.page_end,
                content=item.content,
                score=item.score,
            )
            for item in evidence
        ]
        return ToolResult(
            tool="knowledge_search",
            found=bool(citations),
            data=KnowledgeSearchResult(citations=citations),
            message=(
                "已检索到发布知识证据。"
                if citations
                else "没有找到足够的已发布知识证据。"
            ),
        )
