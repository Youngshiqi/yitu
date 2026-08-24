from asyncio import to_thread
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import func, select, text, union
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.knowledge.embedding import EmbeddingProvider, get_embedding_provider
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.knowledge.tokenization import expand_query_tokens, tokenize_for_query

# 语义向量（qwen）比中文 OR 关键词检索更可靠、噪声更低，故向量权重略高；
# 关键词命中仅作为辅助信号，避免「只沾边某个高频字」的弱相关 chunk 挤占排序。
KEYWORD_WEIGHT = 0.45
VECTOR_WEIGHT = 0.55
MAX_CANDIDATES = 160
# 配置精排器后，先取较大的融合候选池交给精排，再截断到 limit。
RERANK_POOL_SIZE = 30
# 查询向量进程级 LRU：相同 query 不再重复请求嵌入服务（约 2MB 上限）。
_EMBED_CACHE_SIZE = 512


class QueryRewriter(Protocol):
    """把口语化查询改写为检索友好的查询；失败时应回退原查询。"""

    async def rewrite(self, query: str) -> str: ...


class Reranker(Protocol):
    """对融合候选按查询相关性精排；失败时应返回原始顺序。"""

    async def rerank(self, query: str, candidates: list["Evidence"]) -> list["Evidence"]: ...


@lru_cache(maxsize=_EMBED_CACHE_SIZE)
def _embed_query_cached(provider: EmbeddingProvider, query: str) -> tuple[float, ...]:
    """以 provider 实例 + query 为键缓存查询向量；异常不入缓存。"""
    vectors = provider.embed([query])
    if len(vectors) != 1:
        raise RuntimeError("Embedding provider returned an invalid query vector")
    return tuple(vectors[0])


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
        *,
        rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.rewriter = rewriter
        self.reranker = reranker

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[Evidence]:
        """分别召回关键词和向量候选，再按固定权重归一化融合，可选精排。"""
        normalized = query.strip()
        if self.rewriter is not None:
            # 改写失败时回退原查询，绝不阻塞检索主链路。
            normalized = (await self.rewriter.rewrite(normalized)).strip() or query.strip()
        query_tokens = tokenize_for_query(normalized)
        if not normalized or not query_tokens:
            return []

        provider = self.provider or get_embedding_provider()
        query_vector = list(
            await to_thread(_embed_query_cached, cast(Any, provider), normalized)
        )
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
        # 列举型问句追加目录锚点词；以 | 连接的 OR 语义避免停用词零命中后仍因
        # AND 收紧召回，多词命中由 ts_rank_cd 赋予更高排名。
        keyword_tokens = expand_query_tokens(normalized, query_tokens)
        or_query = " | ".join(f"'{token}'" for token in keyword_tokens.split())
        search_query = func.to_tsquery(text("'simple'"), or_query)
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
            .limit(max(1, min(limit, 20)) if self.reranker is None else max(limit, RERANK_POOL_SIZE))
        )
        rows = (await self.session.execute(statement)).all()
        evidence = [
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
        if self.reranker is None or not evidence:
            return evidence[: max(1, min(limit, 20))]
        try:
            ranked = await self.reranker.rerank(normalized, evidence)
        except Exception:  # noqa: BLE001 - 精排失败回退融合排序
            return evidence[: max(1, min(limit, 20))]
        if not ranked:
            return evidence[: max(1, min(limit, 20))]
        return ranked[: max(1, min(limit, 20))]
