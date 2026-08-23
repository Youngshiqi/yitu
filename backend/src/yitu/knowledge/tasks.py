import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity import models as _identity_models  # noqa: F401
from yitu.knowledge.artifacts import MinerUArtifactError, extract_mineru_archive
from yitu.knowledge.blob_store import BlobStore, get_blob_store
from yitu.knowledge.embedding import EmbeddingPermanentError, EmbeddingProvider
from yitu.knowledge.indexing import build_index_version
from yitu.knowledge.mineru_client import (
    MinerUClient,
    MinerUPermanentError,
    MinerURetryableError,
    MinerUTask,
)
from yitu.knowledge.models import DocumentStatus, KnowledgeDocument
from yitu.knowledge.parsers import (
    DocumentParseError,
    DocxParser,
    MinerUParser,
    PlainTextParser,
)
from yitu.knowledge.service import SourceFormat, source_format_from_content_type
from yitu.knowledge.state_machine import resume_parsing, transition
from yitu.platform.config import get_settings
from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError
from yitu.worker import celery_app, run_async

logger = logging.getLogger(__name__)


class MinerUGateway(Protocol):
    """定义 Worker 所需的最小 MinerU 能力，便于注入固定测试实现。"""

    async def submit(self, source_url: str) -> str: ...
    async def get_task(self, task_id: str) -> MinerUTask: ...
    async def download_result(self, url: str) -> bytes: ...


class PollOutcome(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    STOPPED = "stopped"


def _new_mineru_client() -> MinerUClient:
    settings = get_settings()
    if not settings.mineru_token:
        raise MinerUPermanentError("MinerU token is not configured")
    return MinerUClient(
        settings.mineru_base_url,
        settings.mineru_token,
        settings.mineru_model_version,
    )


@asynccontextmanager
async def _mineru_gateway(
    client: MinerUGateway | None,
) -> AsyncIterator[MinerUGateway]:
    if client is not None:
        yield client
        return
    async with _new_mineru_client() as owned_client:
        yield owned_client


async def _locked_document(
    session: AsyncSession, document_id: UUID
) -> KnowledgeDocument:
    document = await session.get(
        KnowledgeDocument,
        document_id,
        with_for_update=True,
    )
    if document is None:
        raise AppError(
            "KNOWLEDGE_DOCUMENT_NOT_FOUND",
            "document not found",
            404,
        )
    return document


async def _mark_parse_failed(document_id: UUID, message: str) -> None:
    """仅把仍在解析链路中的文档标记失败，避免覆盖后续人工状态。"""
    async with SessionFactory() as session, session.begin():
        document = await _locked_document(session, document_id)
        if document.status not in {DocumentStatus.QUEUED, DocumentStatus.PARSING}:
            return
        now = datetime.now(UTC)
        document.status = transition(document.status, DocumentStatus.PARSE_FAILED)
        document.error_message = message
        document.parse_finished_at = now
        document.updated_at = now


def _presign_source(store: BlobStore, object_key: str) -> str:
    try:
        return store.presign_get(object_key, expires_seconds=900)
    except NotImplementedError:
        raise MinerUPermanentError(
            "Knowledge storage does not support external signed URLs"
        ) from None
    except (BotoCoreError, ClientError, OSError):
        raise MinerURetryableError("Knowledge source signing failed temporarily") from None


def _put_artifact(
    store: BlobStore,
    key: str,
    data: bytes,
    content_type: str,
) -> None:
    try:
        store.put(key, data, content_type)
    except (BotoCoreError, ClientError, OSError):
        raise MinerURetryableError("Knowledge artifact storage failed temporarily") from None


def _artifact_keys(document_id: UUID, task_id: str) -> tuple[str, str]:
    # 上游任务 ID 不直接拼入对象键，避免特殊字符改变 COS 路径语义。
    task_fingerprint = sha256(task_id.encode("utf-8")).hexdigest()[:16]
    prefix = f"documents/{document_id}/mineru/{task_fingerprint}"
    return f"{prefix}/result.zip", f"{prefix}/full.md"


_LOCAL_PARSERS: dict[SourceFormat, PlainTextParser | DocxParser] = {
    SourceFormat.MARKDOWN: PlainTextParser("markdown"),
    SourceFormat.TEXT: PlainTextParser("text"),
    SourceFormat.DOCX: DocxParser(),
}


async def _submit_mineru_document(
    document_id: UUID,
    *,
    store: BlobStore | None = None,
    client: MinerUGateway | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> bool:
    """幂等提交解析任务；PDF 走 MinerU，md/txt/docx 本地解析。返回是否需要轮询。"""
    try:
        storage = store or get_blob_store()
    except RuntimeError:
        await _mark_parse_failed(document_id, "Knowledge storage is not configured")
        return False

    try:
        async with SessionFactory() as session, session.begin():
            document = await _locked_document(session, document_id)
            if (
                document.status == DocumentStatus.PARSING
                and document.mineru_task_id
            ):
                # task_id 已提交成功时，重复投递只恢复轮询，不能再次计费。
                logger.info(
                    "恢复 MinerU 任务轮询 document_id=%s task_id=%s",
                    document.id,
                    document.mineru_task_id,
                )
                return True
            if document.status != DocumentStatus.QUEUED:
                return False

            source_format = source_format_from_content_type(document.content_type)
            if source_format is not SourceFormat.PDF:
                return await _parse_local_document(
                    session, storage, document, source_format, embedding_provider
                )
            return await _submit_mineru_pdf(session, storage, document, client)
    except MinerURetryableError:
        raise
    except (MinerUPermanentError, DocumentParseError, EmbeddingPermanentError):
        logger.warning("解析永久失败 document_id=%s", document_id)
        await _mark_parse_failed(document_id, "document parsing failed")
        return False


async def _submit_mineru_pdf(
    session: AsyncSession,
    storage: BlobStore,
    document: KnowledgeDocument,
    client: MinerUGateway | None,
) -> bool:
    """提交 MinerU 解析任务（PDF 路径），返回 True 表示需要轮询。"""
    async with _mineru_gateway(client) as gateway:
        # QUEUED 代表明确的新一轮解析，旧任务和旧产物不能被误复用。
        document.mineru_task_id = None
        document.markdown_artifact_key = None
        document.result_archive_key = None
        document.parse_finished_at = None
        source_url = _presign_source(storage, document.object_key)
        task_id = await gateway.submit(source_url)

        now = datetime.now(UTC)
        document.status = resume_parsing(document.status)
        document.mineru_task_id = task_id
        document.source_artifact_key = document.object_key
        document.parse_started_at = now
        document.parse_attempts += 1
        document.error_message = None
        document.updated_at = now
        logger.info(
            "提交 MinerU 任务 document_id=%s task_id=%s",
            document.id,
            task_id,
        )
        return True


async def _parse_local_document(
    session: AsyncSession,
    storage: BlobStore,
    document: KnowledgeDocument,
    source_format: SourceFormat,
    embedding_provider: EmbeddingProvider | None,
) -> bool:
    """本地解析 md/txt/docx，跳过 MinerU，完成后进入待审核；返回 False 表示无需轮询。"""
    parser = _LOCAL_PARSERS[source_format]
    try:
        raw = storage.open(document.object_key).read()
    except (BotoCoreError, ClientError, OSError):
        raise MinerURetryableError("Knowledge source read failed temporarily") from None

    now = datetime.now(UTC)
    document.status = resume_parsing(document.status)
    document.source_artifact_key = document.object_key
    document.parse_started_at = now
    document.parse_attempts += 1
    document.error_message = None
    document.updated_at = now

    parsed = parser.parse(raw)
    document.parsed_text = parsed.text
    document.parser_name = parsed.parser_name
    document.parser_version = parsed.parser_version
    document.parse_finished_at = now
    await build_index_version(session, document.id, provider=embedding_provider)
    document.status = transition(document.status, DocumentStatus.REVIEW_REQUIRED)
    logger.info(
        "完成本地解析 document_id=%s format=%s",
        document.id,
        source_format.value,
    )
    return False


async def _poll_mineru_document(
    document_id: UUID,
    *,
    store: BlobStore | None = None,
    client: MinerUGateway | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> PollOutcome:
    """使用数据库 task_id 恢复轮询，并以可注入向量模型原子完成解析。"""
    async with SessionFactory() as session, session.begin():
        document = await _locked_document(session, document_id)
        if document.status != DocumentStatus.PARSING:
            return PollOutcome.STOPPED
        task_id = document.mineru_task_id

    if not task_id:
        await _mark_parse_failed(document_id, "MinerU task ID is missing")
        return PollOutcome.STOPPED

    try:
        storage = store or get_blob_store()
    except RuntimeError:
        await _mark_parse_failed(document_id, "Knowledge storage is not configured")
        return PollOutcome.STOPPED

    try:
        async with _mineru_gateway(client) as gateway:
            task = await gateway.get_task(task_id)
            if task.task_id != task_id:
                raise MinerUPermanentError("MinerU task ID does not match")
            state = task.state.lower()
            if state in {"failed", "error", "canceled", "cancelled"}:
                await _mark_parse_failed(document_id, "MinerU parsing failed")
                return PollOutcome.STOPPED
            if state != "done":
                logger.info(
                    "MinerU 任务处理中 document_id=%s task_id=%s",
                    document_id,
                    task_id,
                )
                return PollOutcome.PENDING
            if not task.full_zip_url:
                raise MinerUPermanentError("MinerU result URL is missing")

            archive_data = await gateway.download_result(task.full_zip_url)
            extracted = extract_mineru_archive(archive_data)
            parsed = MinerUParser().parse(extracted.markdown)
            archive_key, markdown_key = _artifact_keys(document_id, task_id)
            _put_artifact(storage, archive_key, archive_data, "application/zip")
            _put_artifact(
                storage,
                markdown_key,
                extracted.markdown,
                "text/markdown; charset=utf-8",
            )

        async with SessionFactory() as session, session.begin():
            document = await _locked_document(session, document_id)
            if (
                document.status != DocumentStatus.PARSING
                or document.mineru_task_id != task_id
            ):
                return PollOutcome.STOPPED

            now = datetime.now(UTC)
            document.parsed_text = parsed.text
            document.parser_name = parsed.parser_name
            document.parser_version = parsed.parser_version
            document.result_archive_key = archive_key
            document.markdown_artifact_key = markdown_key
            document.parse_finished_at = now
            document.updated_at = now
            await build_index_version(
                session,
                document.id,
                provider=embedding_provider,
            )
            document.status = transition(
                document.status,
                DocumentStatus.REVIEW_REQUIRED,
            )
            logger.info(
                "完成 MinerU 解析 document_id=%s task_id=%s",
                document.id,
                task_id,
            )
        return PollOutcome.COMPLETED
    except MinerURetryableError:
        raise
    except (MinerUPermanentError, MinerUArtifactError, EmbeddingPermanentError):
        logger.warning(
            "MinerU 解析永久失败 document_id=%s task_id=%s",
            document_id,
            task_id,
        )
        await _mark_parse_failed(document_id, "MinerU result processing failed")
        return PollOutcome.STOPPED


@celery_app.task(
    name="yitu.submit_mineru_document",
    autoretry_for=(MinerURetryableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=8,
)  # type: ignore[untyped-decorator]
def submit_mineru_document(document_id: str) -> str:
    """提交任务后单独投递轮询，避免 Worker 长时间占用进程。"""
    if run_async(_submit_mineru_document(UUID(document_id))):
        poll_mineru_document.apply_async(args=(document_id,), countdown=5)
    return document_id


@celery_app.task(
    name="yitu.poll_mineru_document",
    autoretry_for=(MinerURetryableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=60,
)  # type: ignore[untyped-decorator]
def poll_mineru_document(document_id: str) -> str:
    """处理中状态通过 Celery 退避重试，完成或永久失败后停止。"""
    outcome = run_async(_poll_mineru_document(UUID(document_id)))
    if outcome == PollOutcome.PENDING:
        raise MinerURetryableError("MinerU task is still processing")
    return document_id
