import logging
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

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


class SourceFormat(str, Enum):
    """知识库文档的源格式，决定解析路径（PDF 走 MinerU，其余本地解析）。"""

    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    DOCX = "docx"


_FORMAT_MIME: dict[SourceFormat, str] = {
    SourceFormat.PDF: "application/pdf",
    SourceFormat.MARKDOWN: "text/markdown",
    SourceFormat.TEXT: "text/plain",
    SourceFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_FORMAT_EXT: dict[SourceFormat, str] = {
    SourceFormat.PDF: "pdf",
    SourceFormat.MARKDOWN: "md",
    SourceFormat.TEXT: "txt",
    SourceFormat.DOCX: "docx",
}


def _is_docx(data: bytes) -> bool:
    """docx 是 ZIP 容器，须包含 word/document.xml。"""
    try:
        with ZipFile(BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except BadZipFile:
        return False


def detect_source_format(filename: str, content_type: str | None, data: bytes) -> SourceFormat:
    """按内容魔数优先、扩展名与 MIME 兜底判定文档格式。"""
    if data.startswith(b"%PDF-"):
        return SourceFormat.PDF
    if data.startswith(b"PK") and _is_docx(data):
        return SourceFormat.DOCX
    name = (filename or "").lower()
    if name.endswith(".md") or content_type in ("text/markdown", "text/x-markdown"):
        return SourceFormat.MARKDOWN
    if name.endswith(".txt") or content_type == "text/plain":
        return SourceFormat.TEXT
    if name.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return SourceFormat.DOCX
    if name.endswith(".pdf") or content_type == "application/pdf":
        return SourceFormat.PDF
    raise AppError(
        "KNOWLEDGE_UNSUPPORTED_FORMAT",
        "unsupported document format; upload PDF, Markdown, TXT or DOCX",
        415,
    )


def source_format_from_content_type(content_type: str | None) -> SourceFormat:
    """从规范化后的 MIME 还原源格式，供解析任务分派；无法识别时按 PDF 兜底。"""
    for fmt, mime in _FORMAT_MIME.items():
        if content_type == mime:
            return fmt
    return SourceFormat.PDF


def validate_document(filename: str, content_type: str | None, data: bytes, max_bytes: int) -> tuple[SourceFormat, int | None]:
    """校验上传字节并返回（源格式, 页数）；非 PDF 页数记为 1。"""
    if len(data) > max_bytes:
        raise AppError("KNOWLEDGE_FILE_TOO_LARGE", "file exceeds upload limit", 413)
    source_format = detect_source_format(filename, content_type, data)
    if source_format == SourceFormat.PDF:
        if b"/Encrypt" in data:
            raise AppError("KNOWLEDGE_ENCRYPTED_PDF", "encrypted PDFs are not supported", 400)
        pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
        return source_format, max(pages, 1)
    return source_format, 1


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
    source_format, page_count = validate_document(filename, content_type, data, max_bytes)
    digest = sha256(data).hexdigest()
    existing = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.sha256 == digest))
    if existing is not None:
        raise AppError("KNOWLEDGE_DOCUMENT_EXISTS", "document already exists", 409, details={"document_id": str(existing.id)})
    mime = _FORMAT_MIME[source_format]
    ext = _FORMAT_EXT[source_format]
    document = KnowledgeDocument(
        id=uuid4(), filename=filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        content_type=mime, size_bytes=len(data), sha256=digest,
        object_key=f"documents/{uuid4()}.{ext}", status=DocumentStatus.UPLOADED,
        page_count=page_count, uploaded_by=uploaded_by,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    try:
        store.put(document.object_key, data, mime)
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
