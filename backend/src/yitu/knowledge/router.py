from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user, require_roles
from yitu.knowledge.blob_store import get_blob_store
from yitu.knowledge.lifecycle import change_document_status
from yitu.knowledge.models import DocumentStatus
from yitu.knowledge.retrieval import KnowledgeRetriever
from yitu.knowledge.retrieval_schemas import EvidenceView, KnowledgeSearchResponse
from yitu.knowledge.schemas import KnowledgeDocumentView, KnowledgeReviewRequest
from yitu.knowledge.service import get_document, upload_document
from yitu.platform.config import get_settings
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
_file = File(...)
_admins = Depends(require_roles(Role.OPERATIONS_ADMIN, Role.SYSTEM_ADMIN))
_session = Depends(get_session)
_authenticated = Depends(get_current_user)


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
    return KnowledgeDocumentView.model_validate(document)


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


@router.post("/documents/{document_id}/reparse", response_model=KnowledgeDocumentView)
async def reparse_document(document_id: UUID, user: CurrentUser = _admins, session: AsyncSession = _session) -> KnowledgeDocumentView:
    document = await change_document_status(session, document_id, user, DocumentStatus.QUEUED)
    await session.commit()
    from yitu.knowledge.tasks import parse_document
    parse_document.delay(str(document.id))
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
