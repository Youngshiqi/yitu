from asyncio import to_thread
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text, union
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.knowledge.embedding import EmbeddingProvider, get_embedding_provider
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.knowledge.tokenization import tokenize_for_search

KEYWORD_WEIGHT = 0.55
VECTOR_WEIGHT = 0.45
MAX_CANDIDATES = 160


@dataclass(frozen=True, slots=True)
class Evidence:
    document_id: UUID
    filename: str
    category: str | None
    index_version: int
    title: str | None
    section_path: list[str]
    content_type: str
    page_start: int | None
    page_end: int | None
    content: str
    score: float


class KnowledgeRetriever:
    """使用 PostgreSQL 全文索引和 pgvector 返回已发布的有效证据。"""

    def __init__(
        self,
        session: AsyncSession,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.provider = provider

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[Evidence]:
        """分别召回关键词和向量候选，再按固定权重归一化融合。"""
        normalized = query.strip()
        query_tokens = tokenize_for_search(normalized)
        if not normalized or not query_tokens:
            return []

        provider = self.provider or get_embedding_provider()
        query_vectors = await to_thread(provider.embed, [normalized])
        if len(query_vectors) != 1:
            raise RuntimeError("Embedding provider returned an invalid query vector")
        query_vector = query_vectors[0]
        candidate_limit = min(max(limit * 8, 40), MAX_CANDIDATES)
        now = datetime.now(UTC)

        latest_versions = (
            select(
                KnowledgeChunk.document_id.label("document_id"),
                func.max(KnowledgeChunk.index_version).label("index_version"),
            )
            .group_by(KnowledgeChunk.document_id)
            .subquery()
        )
        base_ids = (
            select(KnowledgeChunk.id)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .join(
                latest_versions,
                (latest_versions.c.document_id == KnowledgeChunk.document_id)
                & (latest_versions.c.index_version == KnowledgeChunk.index_version),
            )
            .where(KnowledgeDocument.status == DocumentStatus.PUBLISHED)
            .where(
                (KnowledgeDocument.effective_from.is_(None))
                | (KnowledgeDocument.effective_from <= now)
            )
            .where(
                (KnowledgeDocument.effective_to.is_(None))
                | (KnowledgeDocument.effective_to >= now)
            )
        )
        if category:
            base_ids = base_ids.where(KnowledgeDocument.category == category)

        vector_distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
        search_vector = func.to_tsvector(
            text("'simple'"),
            KnowledgeChunk.search_tokens,
        )
        search_query = func.plainto_tsquery(text("'simple'"), query_tokens)
        keyword_rank = func.ts_rank_cd(search_vector, search_query)

        vector_candidates = base_ids.order_by(vector_distance).limit(candidate_limit)
        keyword_candidates = (
            base_ids.where(search_vector.op("@@")(search_query))
            .order_by(keyword_rank.desc())
            .limit(candidate_limit)
        )
        candidate_ids = union(vector_candidates, keyword_candidates).subquery()

        # cosine distance 范围为 0..2；全文 rank 用 rank/(rank+1) 压缩到 0..1。
        vector_score = func.greatest(
            0.0,
            func.least(1.0, 1.0 - (vector_distance / 2.0)),
        )
        keyword_score = keyword_rank / (keyword_rank + 1.0)
        fused_score = (
            (KEYWORD_WEIGHT * keyword_score) + (VECTOR_WEIGHT * vector_score)
        ).label("score")
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, fused_score)
            .join(candidate_ids, candidate_ids.c.id == KnowledgeChunk.id)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeChunk.document_id,
            )
            .order_by(
                fused_score.desc(),
                KnowledgeChunk.document_id,
                KnowledgeChunk.index_version.desc(),
                KnowledgeChunk.chunk_index,
            )
            .limit(max(1, min(limit, 20)))
        )
        rows = (await self.session.execute(statement)).all()
        return [
            Evidence(
                document_id=document.id,
                filename=document.filename,
                category=document.category,
                index_version=chunk.index_version,
                title=chunk.title,
                section_path=chunk.section_path,
                content_type=chunk.content_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content=chunk.content,
                score=round(float(score), 6),
            )
            for chunk, document, score in rows
        ]
