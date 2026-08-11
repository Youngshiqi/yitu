from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.knowledge.blob_store import BlobStore
from yitu.knowledge.models import DocumentStatus, KnowledgeDocument
from yitu.platform.errors import AppError


def validate_pdf(data: bytes, content_type: str | None, max_bytes: int) -> int:
    if len(data) > max_bytes:
        raise AppError("KNOWLEDGE_FILE_TOO_LARGE", "file exceeds upload limit", 413)
    if content_type not in (None, "application/pdf"):
        raise AppError("KNOWLEDGE_INVALID_CONTENT_TYPE", "only PDF files are accepted", 415)
    if not data.startswith(b"%PDF-"):
        raise AppError("KNOWLEDGE_INVALID_PDF", "file is not a valid PDF", 400)
    if b"/Encrypt" in data:
        raise AppError("KNOWLEDGE_ENCRYPTED_PDF", "encrypted PDFs are not supported", 400)
    pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    return max(pages, 1)


async def upload_document(
    session: AsyncSession,
    store: BlobStore,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    uploaded_by: UUID,
    max_bytes: int,
) -> KnowledgeDocument:
    page_count = validate_pdf(data, content_type, max_bytes)
    digest = sha256(data).hexdigest()
    existing = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.sha256 == digest))
    if existing is not None:
        raise AppError("KNOWLEDGE_DOCUMENT_EXISTS", "document already exists", 409, details={"document_id": str(existing.id)})
    document = KnowledgeDocument(
        id=uuid4(), filename=filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        content_type="application/pdf", size_bytes=len(data), sha256=digest,
        object_key=f"documents/{uuid4()}.pdf", status=DocumentStatus.UPLOADED,
        page_count=page_count, uploaded_by=uploaded_by,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    store.put(document.object_key, data)
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def get_document(session: AsyncSession, document_id: UUID) -> KnowledgeDocument:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "document not found", 404)
    return document
