from yitu.knowledge.models import DocumentStatus
from yitu.platform.errors import AppError

_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.QUEUED, DocumentStatus.PARSING}),
    DocumentStatus.QUEUED: frozenset({DocumentStatus.PARSING, DocumentStatus.PARSE_FAILED}),
    DocumentStatus.PARSING: frozenset({DocumentStatus.REVIEW_REQUIRED, DocumentStatus.PARSE_FAILED}),
    DocumentStatus.REVIEW_REQUIRED: frozenset({DocumentStatus.QUEUED}),
    DocumentStatus.PARSE_FAILED: frozenset({DocumentStatus.QUEUED}),
}


def transition(current: DocumentStatus, target: DocumentStatus) -> DocumentStatus:
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise AppError("KNOWLEDGE_INVALID_STATUS_TRANSITION", "invalid document status transition", 409)
    return target
