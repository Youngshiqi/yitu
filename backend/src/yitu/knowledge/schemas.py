from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from yitu.knowledge.models import DocumentStatus


class KnowledgeDocumentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    page_count: int | None
    error_message: str | None
    mineru_task_id: str | None
    source_artifact_key: str | None
    markdown_artifact_key: str | None
    result_archive_key: str | None
    parse_started_at: datetime | None
    parse_finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    published_at: datetime | None
    effective_from: datetime | None
    effective_to: datetime | None
    category: str | None


class KnowledgeReviewRequest(BaseModel):
    category: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
