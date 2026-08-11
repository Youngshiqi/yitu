from datetime import UTC, datetime
from uuid import UUID

from yitu.identity import models as _identity_models  # noqa: F401
from yitu.knowledge.blob_store import get_blob_store
from yitu.knowledge.models import DocumentStatus
from yitu.knowledge.parsers import PyMuPDFParser
from yitu.knowledge.service import get_document
from yitu.knowledge.state_machine import transition
from yitu.platform.database import SessionFactory
from yitu.worker import celery_app, run_async


@celery_app.task(name="yitu.parse_knowledge_document", autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=4)  # type: ignore[untyped-decorator]
def parse_document(document_id: str) -> str:
    run_async(_parse_document(UUID(document_id)))
    return document_id


async def _parse_document(document_id: UUID) -> None:
    async with SessionFactory() as session, session.begin():
        document = await get_document(session, document_id)
        document.status = transition(document.status, DocumentStatus.PARSING)
        document.parse_attempts += 1
        document.updated_at = datetime.now(UTC)
        store = get_blob_store()
        with store.open(document.object_key) as handle:
            parsed = PyMuPDFParser().parse(handle.read())
        document.parsed_text = parsed.text
        document.page_count = parsed.page_count
        document.parser_name = parsed.parser_name
        document.parser_version = parsed.parser_version
        document.status = transition(document.status, DocumentStatus.REVIEW_REQUIRED)
        document.updated_at = datetime.now(UTC)
