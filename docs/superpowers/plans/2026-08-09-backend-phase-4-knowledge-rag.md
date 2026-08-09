# Yitu Backend Phase 4 Knowledge and RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过管理员 HTTP API 完成 PDF 安全上传、异步解析、人工预览、版本发布、中文混合检索和页码引用。

**Architecture:** `BlobStore` 隔离文件存储；Celery Worker 执行 MinerU/PyMuPDF、切片和索引；PostgreSQL 保存工作流事实、全文索引和 pgvector，只有已发布版本可检索。

**Tech Stack:** MinerU、PyMuPDF、jieba、PostgreSQL tsvector/GIN、pgvector、Celery、Docker Volume。

## Global Constraints

- `OPERATIONS_ADMIN` 与 `SYSTEM_ADMIN` 可管理文档生命周期；只有 `SYSTEM_ADMIN` 可改解析/Embedding/索引配置和重放死信。
- 原始文件不存数据库；文件名不得成为存储路径；未发布内容不得进入 Agent 检索。
- 阶段开始需要 MinerU 下载时，先向用户说明磁盘、网络、时间和验证方式。

---

### Task 1: BlobStore and Safe PDF Upload

**Files:** Create `backend/src/yitu/knowledge/{blob_store,models,schemas,service,router}.py`; migration `0016`; tests `backend/tests/knowledge/test_upload.py`; modify Compose volumes.

**Interfaces:** Produces `BlobStore.put/open/delete`, `POST /api/v1/knowledge/documents`, document status API.

- [ ] Test streaming upload, PDF header/MIME/size/page/encryption checks, SHA-256 dedupe, path traversal and role matrix.
- [ ] Run knowledge upload tests; expect missing module.
- [ ] Implement local-volume BlobStore with generated object keys and metadata-only database rows.
- [ ] Run migration and upload tests; expect all pass.
- [ ] Commit `feat: add secure knowledge uploads`.

### Task 2: Parser Worker and Durable Status Machine

**Files:** Create `backend/src/yitu/knowledge/{parsers,tasks,state_machine}.py`; migration `0017`; tests `backend/tests/knowledge/test_parsing.py`.

**Interfaces:** Produces `MinerUParser`, `PyMuPDFParser`, `parse_document(document_id)`, statuses `UPLOADED/QUEUED/PARSING/REVIEW_REQUIRED/PARSE_FAILED`.

- [ ] Test text, scan fixture, corrupt file, timeout, five retries, fallback warning and Worker restart recovery.
- [ ] Run parser tests with fixed parser adapters; expect missing parser contracts.
- [ ] Implement subprocess/container boundary, resource limits, structured parse artifacts and PyMuPDF text-only fallback.
- [ ] Run parser tests; run one explicitly approved local MinerU smoke fixture; expect review-required result.
- [ ] Commit `feat: parse PDF knowledge asynchronously`.

### Task 3: Chunking, Versioned Embeddings, and Index Build

**Files:** Create `backend/src/yitu/knowledge/{chunking,embedding,indexing}.py`; migration `0018`; tests `backend/tests/knowledge/test_chunking.py`, `test_indexing.py`.

**Interfaces:** Produces `ChunkingPolicy.chunk()`, `EmbeddingProvider.embed()`, `build_index_version()`.

- [ ] Test heading/table boundaries, 500–800 Chinese-character split, page/coordinates, header cleanup, vector dimension and mixed-version rejection.
- [ ] Run chunk/index tests; expect missing policies.
- [ ] Implement deterministic chunker, fixed embedding adapter for CI, jieba tokens, tsvector and separate vector index versions.
- [ ] Run migration and tests; expect all pass.
- [ ] Commit `feat: build versioned knowledge indexes`.

### Task 4: Preview, Review, Publish, Archive, and Reparse APIs

**Files:** Modify knowledge service/router/schemas; tests `backend/tests/knowledge/test_review_publish.py`.

**Interfaces:** Produces preview/artifact routes and `review`, `publish`, `archive`, `deactivate`, `reparse` actions.

- [ ] Test both admin roles, system-only config mutation, required reviewer, atomic new-version switch, failed-new-version fallback and audit records.
- [ ] Run review tests; expect missing actions.
- [ ] Implement explicit lifecycle commands; never publish automatically after parsing/indexing.
- [ ] Run tests; expect all pass.
- [ ] Commit `feat: add reviewed knowledge publishing`.

### Task 5: Hybrid Retrieval and Verifiable Citations

**Files:** Create `backend/src/yitu/knowledge/retrieval.py`; create query routes; tests `backend/tests/knowledge/test_retrieval.py`.

**Interfaces:** Produces `KnowledgeRetriever.search(query, filters, limit) -> list[Evidence]`; evidence includes document/version/title/page/coordinates/snippet/scores.

- [ ] Test Chinese keywords, synonyms, semantic questions, role/effective-date filters, unpublished exclusion and evidence-poor refusal signal.
- [ ] Run retrieval tests; expect missing retriever.
- [ ] Implement normalized keyword/vector weighted fusion and stable score breakdown; reserve an injected reranker without enabling it.
- [ ] Run retrieval tests; expect all quality fixtures meet recorded thresholds.
- [ ] Commit `feat: add cited hybrid knowledge retrieval`.

### Task 6: RAG Phase Gate

**Files:** Create `backend/tests/journeys/test_knowledge_pipeline.py`; add test PDF fixtures and README knowledge section.

**Interfaces:** Produces HTTP-only upload-to-citation journey.

- [ ] Test upload → parse → preview → publish → retrieve, old-version service continuity, injection document isolation and correct citation page.
- [ ] Run `cd backend; uv run ruff check .; uv run mypy src; uv run pytest tests/knowledge tests/journeys/test_knowledge_pipeline.py -q`.
- [ ] Run migration round-trip and Compose Worker recovery test; expect all pass.
- [ ] Record parser/index versions and fixture hashes in the test report.
- [ ] Commit `test: verify managed RAG pipeline`.
