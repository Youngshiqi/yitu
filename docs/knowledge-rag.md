# Knowledge and RAG

## Lifecycle

Documents move through the following explicit states:

`UPLOADED -> PARSING -> REVIEW_REQUIRED -> PUBLISHED`

Parsing failures use `PARSE_FAILED` and can be requeued. Published documents can be `ARCHIVED` or `DEACTIVATED`. Only published documents inside their effective time window are searchable.

## Admin API

All lifecycle endpoints require an `OPERATIONS_ADMIN` or `SYSTEM_ADMIN` bearer token.

```text
POST /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents/{document_id}
POST /api/v1/knowledge/documents/{document_id}/review
POST /api/v1/knowledge/documents/{document_id}/publish
POST /api/v1/knowledge/documents/{document_id}/archive
POST /api/v1/knowledge/documents/{document_id}/deactivate
POST /api/v1/knowledge/documents/{document_id}/reparse
```

Review payload:

```json
{
  "category": "delivery-rules",
  "effective_from": "2026-08-11T00:00:00+08:00",
  "effective_to": null
}
```

## Search API

Authenticated users can search published evidence:

```text
GET /api/v1/knowledge/search?query=派送时效&category=delivery-rules&limit=5
```

Each result includes the source document, index version, page range, text fragment, and a normalized score. The current local embedding provider is deterministic and intended for development; production can replace it behind the `EmbeddingProvider` interface.
