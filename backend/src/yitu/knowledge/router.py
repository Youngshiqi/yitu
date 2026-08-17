from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user, require_roles
from yitu.knowledge.blob_store import get_blob_store
from yitu.knowledge.lifecycle import change_document_status
from yitu.knowledge.models import DocumentStatus, KnowledgeDocument
from yitu.knowledge.retrieval import KnowledgeRetriever
from yitu.knowledge.retrieval_schemas import EvidenceView, KnowledgeSearchResponse
from yitu.knowledge.schemas import (
    KnowledgeDocumentContentView,
    KnowledgeDocumentView,
    KnowledgeReviewRequest,
)
from yitu.knowledge.service import delete_document, get_document, upload_document
from yitu.platform.config import get_settings
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
_file = File(...)
_session = Depends(get_session)
_authenticated = Depends(get_current_user)


def admin_user(current_user: CurrentUser = _authenticated) -> CurrentUser:
    return require_roles(Role.OPERATIONS_ADMIN)(current_user)


_admins = Depends(admin_user)


@router.post("/documents", response_model=KnowledgeDocumentView, status_code=201)
async def upload_knowledge_document(
    file: UploadFile = _file,
    user: CurrentUser = _admins,
    session: AsyncSession = _session,
) -> KnowledgeDocumentView:
    data = await file.read()
    document = await upload_document(
        session, get_blob_store(), filename=file.filename or "document.pdf",
        content_type=file.content_type, data=data, uploaded_by=user.id,
        max_bytes=get_settings().knowledge_max_upload_bytes,
    )
    # 原文件提交成功后再进入异步队列，避免 Worker 读取尚未持久化的对象。
    document.status = DocumentStatus.QUEUED
    document.updated_at = datetime.now(UTC)
    await session.commit()
    from yitu.knowledge.tasks import submit_mineru_document

    submit_mineru_document.delay(str(document.id))
    await session.refresh(document)
    return KnowledgeDocumentView.model_validate(document)


@router.get("/documents", response_model=list[KnowledgeDocumentView])
async def list_knowledge_documents(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: CurrentUser = _admins,
    session: AsyncSession = _session,
) -> list[KnowledgeDocumentView]:
    result = await session.scalars(
        select(KnowledgeDocument)
        .order_by(KnowledgeDocument.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [KnowledgeDocumentView.model_validate(item) for item in result.all()]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentView)
async def knowledge_document_status(
    document_id: UUID,
    _user: CurrentUser = _admins,
    session: AsyncSession = _session,
) -> KnowledgeDocumentView:
    return KnowledgeDocumentView.model_validate(await get_document(session, document_id))


async def _lifecycle(document_id: UUID, user: CurrentUser, session: AsyncSession, target: DocumentStatus, review: KnowledgeReviewRequest | None = None) -> KnowledgeDocumentView:
    document = await change_document_status(session, document_id, user, target, review)
    await session.commit()
    await session.refresh(document)
    return KnowledgeDocumentView.model_validate(document)


@router.post("/documents/{document_id}/review", response_model=KnowledgeDocumentView)
async def review_document(document_id: UUID, payload: KnowledgeReviewRequest, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    return await _lifecycle(document_id, user, session, DocumentStatus.REVIEW_REQUIRED, payload)


@router.post("/documents/{document_id}/publish", response_model=KnowledgeDocumentView)
async def publish_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    return await _lifecycle(document_id, user, session, DocumentStatus.PUBLISHED)


@router.post("/documents/{document_id}/archive", response_model=KnowledgeDocumentView)
async def archive_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    return await _lifecycle(document_id, user, session, DocumentStatus.ARCHIVED)


@router.post("/documents/{document_id}/deactivate", response_model=KnowledgeDocumentView)
async def deactivate_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    return await _lifecycle(document_id, user, session, DocumentStatus.DEACTIVATED)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_knowledge_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> Response:
    """删除文档、索引分块及对象存储中的原始文件与解析产物。"""
    await delete_document(session, get_blob_store(), document_id, user)
    return Response(status_code=204)


@router.post("/documents/{document_id}/reparse", response_model=KnowledgeDocumentView)
async def reparse_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    document = await change_document_status(session, document_id, user, DocumentStatus.QUEUED)
    await session.commit()
    from yitu.knowledge.tasks import submit_mineru_document
    submit_mineru_document.delay(str(document.id))
    await session.refresh(document)
    return KnowledgeDocumentView.model_validate(document)


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str = Query(min_length=1, max_length=500),
    category: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=5, ge=1, le=20),
    _user: CurrentUser = _authenticated,
    session: AsyncSession = _session,
) -> KnowledgeSearchResponse:
    items = await KnowledgeRetriever(session).search(query, category=category, limit=limit)
    return KnowledgeSearchResponse(items=[EvidenceView.model_validate(item) for item in items])


@router.get("/documents/{document_id}/content", response_model=KnowledgeDocumentContentView)
async def knowledge_document_content(
    document_id: UUID,
    _user: CurrentUser = _admins,
    session: AsyncSession = _session,
) -> KnowledgeDocumentContentView:
    """返回解析后的 Markdown 正文，供运营管理员预览。"""
    document = await get_document(session, document_id)
    return KnowledgeDocumentContentView(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        content=document.parsed_text or "",
        page_count=document.page_count,
    )


@router.get("/documents/{document_id}/file")
async def knowledge_document_file(
    document_id: UUID,
    _user: CurrentUser = _admins,
    session: AsyncSession = _session,
) -> Response:
    """返回上传的原始 PDF 字节流，解析完成前用于回退预览。"""
    document = await get_document(session, document_id)
    data = get_blob_store().open(document.object_key).read()
    return Response(content=data, media_type="application/pdf")
