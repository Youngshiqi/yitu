from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.knowledge.embedding import DeterministicEmbedding
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument


@dataclass(frozen=True, slots=True)
class Evidence:
    document_id: UUID
    filename: str
    category: str | None
    index_version: int
    page_start: int | None
    page_end: int | None
    content: str
    score: float


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_left = sqrt(sum(value * value for value in left)) or 1.0
    norm_right = sqrt(sum(value * value for value in right)) or 1.0
    return dot / (norm_left * norm_right)


class KnowledgeRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, *, category: str | None = None, limit: int = 5) -> list[Evidence]:
        normalized = query.strip()
        if not normalized:
            return []
        now = datetime.now(UTC)
        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeDocument.status == DocumentStatus.PUBLISHED)
            .where((KnowledgeDocument.effective_from.is_(None)) | (KnowledgeDocument.effective_from <= now))
            .where((KnowledgeDocument.effective_to.is_(None)) | (KnowledgeDocument.effective_to >= now))
        )
        if category:
            statement = statement.where(KnowledgeDocument.category == category)
        rows = (await self.session.execute(statement)).all()
        query_vector = DeterministicEmbedding().embed([normalized])[0]
        terms = set(normalized.lower().split())
        scored: list[Evidence] = []
        for chunk, document in rows:
            keyword_hits = sum(term in chunk.content.lower() for term in terms)
            keyword_score = keyword_hits / max(len(terms), 1)
            vector_score = (_cosine(query_vector, chunk.embedding) + 1.0) / 2.0
            score = (0.55 * keyword_score) + (0.45 * vector_score)
            if score <= 0:
                continue
            scored.append(Evidence(document.id, document.filename, document.category, chunk.index_version, chunk.page_start, chunk.page_end, chunk.content, round(score, 6)))
        scored.sort(key=lambda item: (-item.score, str(item.document_id), item.index_version))
        return scored[: max(1, min(limit, 20))]
