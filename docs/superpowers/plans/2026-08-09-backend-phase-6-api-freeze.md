# Yitu Backend Phase 6 API Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成全量后端验证、确定性演示、性能与安全基线，并冻结可供前端生成类型的 OpenAPI v1。

**Architecture:** 不增加新业务范围，只修复跨阶段一致性并产出机器可验证契约和人工可读文档。API 快照与错误/权限目录共同成为前端基线。

**Tech Stack:** 全部后端栈、OpenAPI JSON、openapi-typescript 验证工具、pytest、Docker Compose。

## Global Constraints

- 本阶段禁止顺便开发 Vue；禁止为文档绕过实际响应模型。
- 所有完成声明必须基于本轮新运行的验证结果。
- 破坏性契约修正必须在冻结前完成，并同步旅程测试。

---

### Task 1: Migration and Data Integrity Rehearsal

**Files:** Create `backend/tests/migrations/test_full_history.py`; update inconsistent migrations/models only when tests expose a mismatch.

**Interfaces:** Produces verified empty-db upgrade, downgrade policy and schema/model parity report.

- [ ] Test empty upgrade, seeded upgrade, constraints/indexes/extensions and allowed downgrade boundary.
- [ ] Run migration tests against a fresh PostgreSQL database; record failures before changes.
- [ ] Fix ordering, naming or data migrations without editing already-released semantics silently.
- [ ] Re-run migration tests and `alembic check`; expect exit 0.
- [ ] Commit `test: verify complete migration history`.

### Task 2: Deterministic Demo Seed, Clock, Advance, and Scoped Reset

**Files:** Complete `backend/src/yitu/demo/{seed,router,scenarios}.py`; migration if needed; tests `backend/tests/journeys/test_demo_reset.py`.

**Interfaces:** Produces `POST /api/v1/demo/reset`, scenario advance routes and seven stable demo identity keys.

- [ ] Test demo-only 404, system-admin reset, scoped deletion, two identical resets and non-demo row preservation.
- [ ] Run demo tests; expect failures for incomplete scenario coverage.
- [ ] Implement deterministic IDs/numbers where promised, injected Clock advancement and scope-tagged reset transactions.
- [ ] Run two complete Beijing–Shanghai journeys with reset between them; expect identical observable results.
- [ ] Commit `feat: add repeatable backend demo scenarios`.

### Task 3: Cross-Module Security and Performance Baseline

**Files:** Create `backend/tests/security/test_matrix.py`, `backend/tests/performance/test_baseline.py`; create `docs/backend/security-baseline.md`.

**Interfaces:** Produces recorded authorization matrix, query-count limits and representative P95 baseline commands.

- [ ] Generate cases for unauthenticated, wrong role/station/owner/state, replay, file abuse, prompt injection and secret leakage.
- [ ] Add bounded performance cases for list/detail, tracking, hybrid retrieval and fixed-model Agent response; fail on accidental N+1 thresholds.
- [ ] Run security/performance suites in Compose and record environment plus results.
- [ ] Fix only evidenced correctness/performance regressions and rerun fresh.
- [ ] Commit `test: establish backend security and performance baseline`.

### Task 4: OpenAPI Normalization and Contract Snapshot

**Files:** Create `backend/scripts/export_openapi.py`; create `docs/api/openapi-v1.json`, `errors.md`, `permissions.md`, `examples.md`; create `backend/tests/api/test_openapi_contract.py`.

**Interfaces:** Produces frozen `/api/v1` operation IDs, schemas, errors, examples, pagination and SSE/file workflow documentation.

- [ ] Test unique operation IDs, explicit response models/statuses, no undocumented 2xx, stable error envelope and no secret-bearing fields.
- [ ] Export OpenAPI and inspect naming/pagination/filter conventions; tests must identify every inconsistency precisely.
- [ ] Normalize routers/schemas and document role/resource matrix, idempotency, async states and Agent tool relation.
- [ ] Re-export twice and assert byte-stable JSON snapshot.
- [ ] Commit `docs: freeze OpenAPI v1 contract`.

### Task 5: Frontend Type Generation Compatibility

**Files:** Create `tools/api-contract/package.json`; create `tools/api-contract/typecheck.ts`; modify API docs.

**Interfaces:** Proves a TypeScript client can be generated from `openapi-v1.json` without schema errors.

- [ ] Configure pinned `openapi-typescript` and a compile-only consumer for representative auth, shipment, upload, SSE and Agent DTOs.
- [ ] Run `cd tools/api-contract; npm install; npm run generate; npm run typecheck`; expect exit 0.
- [ ] Fix OpenAPI source models rather than hand-editing generated output.
- [ ] Repeat generation from a clean directory and compare output.
- [ ] Commit `test: verify frontend API type generation`.

### Task 6: Final Backend Gate and Handoff

**Files:** Update `README.md`, `CONTEXT.md`; create `docs/backend/verification-report.md`, `frontend-handoff.md`.

**Interfaces:** Produces one-command startup, demo script, troubleshooting, verification evidence and frozen frontend handoff.

- [ ] From clean containers run `docker compose up --build -d` and `alembic upgrade head`; verify all health checks.
- [ ] Run `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`; record exact counts and versions.
- [ ] Run four logistics journeys, an exception/return journey, RAG upload-to-citation, fixed Agent eval and approved online smoke.
- [ ] Run demo reset twice and regenerate OpenAPI/types; verify deterministic outputs.
- [ ] Commit `docs: hand off frozen backend API` only after every fresh command exits 0.
