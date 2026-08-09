# Yitu Backend Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可通过 Docker Compose 运行、具备数据库迁移、统一时间、错误、幂等、审计和异步任务骨架的 FastAPI 后端。

**Architecture:** `platform` 提供跨模块基础能力，业务模块只能依赖这些稳定接口。PostgreSQL 是事实源，Redis 只作为 Celery broker/backend，API 与 Worker 使用相同配置和数据库模型。

**Tech Stack:** Python 3.11、uv、FastAPI、Pydantic v2、SQLAlchemy 2 async、Alembic、PostgreSQL 16 + pgvector、Redis 7、Celery、pytest、HTTPX、Ruff、mypy、Docker Compose。

## Global Constraints

- 遵守 `.CLAUDE` 与完整后端设计；业务时间固定为 `Asia/Shanghai`。
- 包布局使用 `backend/src/yitu`，测试使用真实 PostgreSQL。
- 新增注释与 docstring 使用简体中文。
- 本阶段不实现具体物流业务和前端。

---

### Task 1: Python Project and Health API

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/yitu/__init__.py`
- Create: `backend/src/yitu/main.py`
- Create: `backend/tests/api/test_health.py`
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`, `GET /api/v1/health -> HealthResponse`

- [ ] **Step 1: Write the failing HTTP test**

```python
async def test_health_reports_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Verify red**

Run: `cd backend; uv run pytest tests/api/test_health.py -q`
Expected: test collection fails because `yitu.main` does not exist.

- [ ] **Step 3: Add the minimal package and app factory**

Configure runtime and dev dependencies, pytest asyncio mode, Ruff and mypy. Implement `HealthResponse` and `create_app()` with the versioned health route.

- [ ] **Step 4: Verify green**

Run: `cd backend; uv run ruff check .; uv run mypy src; uv run pytest tests/api/test_health.py -q`
Expected: all commands exit 0 and one test passes.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "chore: scaffold FastAPI backend"
```

### Task 2: Typed Configuration, Clock, and Error Contract

**Files:**
- Create: `backend/src/yitu/platform/config.py`
- Create: `backend/src/yitu/platform/clock.py`
- Create: `backend/src/yitu/platform/errors.py`
- Create: `backend/src/yitu/platform/schemas.py`
- Create: `backend/tests/platform/test_clock.py`
- Create: `backend/tests/api/test_errors.py`
- Modify: `backend/src/yitu/main.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `Clock.now()`, `to_business_timezone()`, `AppError`, `ErrorResponse`

- [ ] **Step 1: Write failing contracts**

Test that UTC midnight converts to `2026-08-09T08:00:00+08:00`, naive datetimes are rejected, and `AppError("INVALID_INPUT", ..., 422)` returns `code`, Chinese `message`, `request_id`, and `details`.

- [ ] **Step 2: Verify red**

Run: `cd backend; uv run pytest tests/platform/test_clock.py tests/api/test_errors.py -q`
Expected: imports fail for missing platform modules.

- [ ] **Step 3: Implement shared contracts**

Use `ZoneInfo("Asia/Shanghai")`, a cached Pydantic Settings factory, timezone-aware response base model, request ID middleware, and a FastAPI exception handler for `AppError`.

- [ ] **Step 4: Verify green**

Run: `cd backend; uv run pytest tests/platform/test_clock.py tests/api/test_errors.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/yitu/platform backend/src/yitu/main.py backend/tests
git commit -m "feat: add shared time and error contracts"
```

### Task 3: PostgreSQL, SQLAlchemy, and Alembic

**Files:**
- Create: `backend/src/yitu/platform/database.py`
- Create: `backend/src/yitu/platform/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_create_platform_tables.py`
- Create: `backend/tests/platform/test_database.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `Base`, `SessionFactory`, `get_session()`, `transactional_session()`

- [ ] **Step 1: Write PostgreSQL integration tests**

Assert the connection reports `Asia/Shanghai`, `SELECT now()` is timezone-aware, transactions roll back on exception, and pgvector extension is available.

- [ ] **Step 2: Verify red**

Run: `cd backend; uv run pytest tests/platform/test_database.py -q`
Expected: database imports or connection fixture fail.

- [ ] **Step 3: Implement database foundation**

Create the async engine and session factory, set the session timezone on connection, share one declarative `Base`, and configure Alembic to import metadata. Migration `0001` enables `vector` and creates migration-owned platform metadata.

- [ ] **Step 4: Verify green and migration round-trip**

Run: `cd backend; uv run alembic upgrade head; uv run pytest tests/platform/test_database.py -q; uv run alembic downgrade base; uv run alembic upgrade head`
Expected: every command exits 0.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: configure PostgreSQL persistence"
```

### Task 4: Idempotency and Audit Foundations

**Files:**
- Create: `backend/src/yitu/platform/idempotency.py`
- Create: `backend/src/yitu/platform/audit.py`
- Create: `backend/migrations/versions/0002_create_idempotency_and_audit.py`
- Create: `backend/tests/platform/test_idempotency.py`
- Create: `backend/tests/platform/test_audit.py`

**Interfaces:**
- Produces: `IdempotencyService.execute(scope, key, request_hash, operation)`, `AuditService.record(...)`

- [ ] **Step 1: Write failing replay and conflict tests**

Verify identical key/hash replays the stored response, identical key with different hash raises `IDEMPOTENCY_KEY_REUSED`, concurrent execution stores one result, and audit entries cannot be updated through the service.

- [ ] **Step 2: Verify red**

Run: `cd backend; uv run pytest tests/platform/test_idempotency.py tests/platform/test_audit.py -q`
Expected: missing services and tables.

- [ ] **Step 3: Implement atomic records**

Use a unique `(scope, key)` constraint, canonical JSON SHA-256 request hashes, response status/body snapshots, and append-only audit rows containing actor, action, resource, before/after summary, reason, request ID and time.

- [ ] **Step 4: Verify green**

Run: `cd backend; uv run alembic upgrade head; uv run pytest tests/platform/test_idempotency.py tests/platform/test_audit.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: add idempotency and audit foundations"
```

### Task 5: Outbox, Celery, and Dead Letters

**Files:**
- Create: `backend/src/yitu/platform/outbox.py`
- Create: `backend/src/yitu/platform/tasks.py`
- Create: `backend/src/yitu/worker.py`
- Create: `backend/migrations/versions/0003_create_outbox_and_dead_letters.py`
- Create: `backend/tests/platform/test_outbox.py`
- Create: `backend/tests/platform/test_worker_recovery.py`

**Interfaces:**
- Produces: `OutboxService.append()`, `relay_pending_events()`, `consume_once()`, `DeadLetterService.replay()`

- [ ] **Step 1: Write failing reliability tests**

Assert event and aggregate rollback together, duplicate delivery changes observable state once, five failures create a dead letter, and replay preserves the original idempotency key.

- [ ] **Step 2: Verify red**

Run: `cd backend; uv run pytest tests/platform/test_outbox.py tests/platform/test_worker_recovery.py -q`
Expected: missing outbox and worker modules.

- [ ] **Step 3: Implement durable task state**

Persist event ID, type, payload, attempts, next attempt and status in PostgreSQL. Configure Celery with Redis but keep delivery state in PostgreSQL; apply exponential backoff, jitter and a five-attempt dead-letter transition.

- [ ] **Step 4: Verify green**

Run: `cd backend; uv run alembic upgrade head; uv run pytest tests/platform/test_outbox.py tests/platform/test_worker_recovery.py -q`
Expected: all tests pass without a real cloud dependency.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: add durable outbox processing"
```

### Task 6: Docker Compose and Phase Gate

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `.gitattributes`
- Create: `compose.yaml`
- Create: `backend/Dockerfile`
- Create: `README.md`
- Create: `CONTEXT.md`
- Create: `backend/tests/api/test_readiness.py`
- Modify: `backend/src/yitu/main.py`

**Interfaces:**
- Produces: Compose services `db`, `redis`, `api`, `worker`; `GET /api/v1/readiness`

- [ ] **Step 1: Ask the user to start Docker Desktop**

Explain how to open Docker Desktop and wait until the engine reports running. Verify with `docker info`; do not continue Compose checks while the engine is unavailable.

- [ ] **Step 2: Write readiness test and container definitions**

The readiness route must check PostgreSQL and Redis with bounded timeouts. Compose uses PostgreSQL 16 with pgvector, Redis 7, API and Worker health checks, named volumes, and no committed secrets.

- [ ] **Step 3: Build and migrate**

Run: `docker compose up --build -d; docker compose exec api uv run alembic upgrade head`
Expected: all four services become healthy and migrations reach head.

- [ ] **Step 4: Run the complete phase gate**

Run: `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`
Run: `docker compose ps; Invoke-RestMethod http://localhost:8000/api/v1/readiness`
Expected: checks exit 0, tests pass, services are healthy, readiness returns `{"status":"ready"}`.

- [ ] **Step 5: Commit**

```bash
git add .gitattributes .gitignore .env.example compose.yaml README.md CONTEXT.md backend
git commit -m "chore: deliver runnable backend foundation"
```
