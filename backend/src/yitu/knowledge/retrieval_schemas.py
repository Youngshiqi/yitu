from uuid import UUID

from pydantic import BaseModel


class EvidenceView(BaseModel):
    document_id: UUID
    filename: str
    category: str | None
    index_version: int
    page_start: int | None
    page_end: int | None
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    items: list[EvidenceView]
