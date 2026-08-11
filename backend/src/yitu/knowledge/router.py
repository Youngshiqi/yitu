from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_roles
from yitu.knowledge.blob_store import get_blob_store
from yitu.knowledge.schemas import KnowledgeDocumentView
from yitu.knowledge.service import get_document, upload_document
from yitu.platform.config import get_settings
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
_file = File(...)
_admins = Depends(require_roles(Role.OPERATIONS_ADMIN, Role.SYSTEM_ADMIN))
_session = Depends(get_session)


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
