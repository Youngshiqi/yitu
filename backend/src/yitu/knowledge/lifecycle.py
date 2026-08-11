from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.knowledge.schemas import KnowledgeReviewRequest
from yitu.knowledge.state_machine import transition
from yitu.platform.errors import AppError


async def change_document_status(session: AsyncSession, document_id: UUID, user: CurrentUser, target: DocumentStatus, review: KnowledgeReviewRequest | None = None) -> KnowledgeDocument:
    if user.role not in {Role.OPERATIONS_ADMIN, Role.SYSTEM_ADMIN}:
        raise AppError("FORBIDDEN_ROLE", "role is not allowed", 403)
    document = await session.get(KnowledgeDocument, document_id, with_for_update=True)
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "document not found", 404)
    now = datetime.now(UTC)
    if target == DocumentStatus.REVIEW_REQUIRED and document.status == DocumentStatus.REVIEW_REQUIRED:
        document.status = target
    else:
        document.status = transition(document.status, target)
    document.updated_at = now
    if target == DocumentStatus.PUBLISHED:
        if document.reviewed_by is None:
            raise AppError("KNOWLEDGE_REVIEW_REQUIRED", "document must be reviewed before publishing", 409)
        document.published_at = now
    elif target == DocumentStatus.QUEUED:
        await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        document.parsed_text = None
        document.parser_name = None
        document.parser_version = None
        document.error_message = None
    if review is not None:
        document.reviewed_by = user.id
        document.reviewed_at = now
        document.category = review.category
        document.effective_from = review.effective_from
        document.effective_to = review.effective_to
    return document
