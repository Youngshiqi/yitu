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
    created_at: datetime
    updated_at: datetime
