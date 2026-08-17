import logging
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.knowledge.blob_store import BlobStore
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.platform.errors import AppError

logger = logging.getLogger(__name__)


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
    try:
        store.put(document.object_key, data, "application/pdf")
    except (BotoCoreError, ClientError, OSError):
        # 外部存储异常统一转换，API 不泄露 COS 请求、桶名或签名细节。
        raise AppError(
            "KNOWLEDGE_STORAGE_UNAVAILABLE",
            "knowledge storage is temporarily unavailable",
            503,
        ) from None
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def get_document(session: AsyncSession, document_id: UUID) -> KnowledgeDocument:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "document not found", 404)
    return document


async def delete_document(
    session: AsyncSession,
    store: BlobStore,
    document_id: UUID,
    user: CurrentUser,
) -> None:
    """删除文档、索引分块及对象存储中的原始文件与解析产物。"""
    if user.role is not Role.OPERATIONS_ADMIN:
        raise AppError("FORBIDDEN_ROLE", "role is not allowed", 403)
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "document not found", 404)
    object_keys = [
        key
        for key in (
            document.object_key,
            document.source_artifact_key,
            document.markdown_artifact_key,
            document.result_archive_key,
        )
        if key
    ]
    await session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    )
    await session.delete(document)
    await session.commit()
    # 数据库删除已提交，对象清理失败不应让删除接口报错，残留对象可离线回收。
    for key in object_keys:
        try:
            store.delete(key)
        except (BotoCoreError, ClientError, OSError):
            logger.warning("failed to delete knowledge blob object %s", key)
