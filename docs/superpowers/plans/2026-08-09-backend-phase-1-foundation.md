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

### Task 5：可靠异步任务基础

Task 5 拆成 7 个可独立验收的小任务。整个 Task 5 最多新增 5 个核心行为测试，不逐列测试数据库结构，也不测试 Celery 框架本身。

#### Task 5.1：Outbox 与死信数据库迁移

**文件：**
- 新建：`backend/migrations/versions/0003_create_outbox_and_dead_letters.py`

**产出：**
- `outbox_events`：保存 `id`、`event_type`、`business_id`、`payload`、`idempotency_key`、`status`、`attempts`、`next_attempt_at`、`last_error`、`created_at`、`processed_at`
- `dead_letters`：保存原事件 ID、任务类型、业务 ID、载荷、原幂等键、尝试次数、最后错误、失败时间、重放时间和处理建议

- [ ] 编写 `0003` 迁移，前置版本固定为 `0002`；时间列使用 `timestamptz`，载荷使用 `JSONB`。
- [ ] 执行 `cd backend; uv run alembic upgrade head`，确认当前版本为 `0003`。
- [ ] 执行 `uv run alembic downgrade 0002; uv run alembic upgrade head`，确认迁移可以往返。
- [ ] 不新增逐列结构测试；后续真实写入行为会覆盖表结构。
- [ ] 提交：`功能：新增 Outbox 与死信数据表`

#### Task 5.2：事务内追加 Outbox 事件

**文件：**
- 新建：`backend/src/yitu/platform/outbox.py`
- 新建或修改：`backend/tests/platform/test_outbox.py`

**接口：**
- `OutboxService(session, clock).append(event_type, business_id, payload, idempotency_key) -> UUID`

- [ ] 只写 1 个失败测试：在同一事务写入业务探针和 Outbox 事件，随后主动抛错，验证二者一起回滚。
- [ ] 实现 `append()`；只执行插入，不自行 `commit`，初始状态为 `pending`、尝试次数为 `0`。
- [ ] 运行该聚焦测试并确认通过。
- [ ] 提交：`功能：支持事务内追加 Outbox 事件`

#### Task 5.3：投递到期事件

**文件：**
- 修改：`backend/src/yitu/platform/outbox.py`
- 修改：`backend/tests/platform/test_outbox.py`

**接口：**
- `relay_pending_events(session_factory, publish, limit=100) -> int`
- `publish(event_id: UUID) -> Awaitable[None]`

- [ ] 只写 1 个失败测试：仅投递状态为 `pending` 且 `next_attempt_at` 已到期的事件；未来事件不得投递。
- [ ] 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 领取事件，发布成功后改为 `published`。
- [ ] 发布失败时保留为 `pending`，不得丢失数据库事件。
- [ ] 运行聚焦测试并确认通过。
- [ ] 提交：`功能：新增 Outbox 到期事件中继`

#### Task 5.4：幂等消费单个事件

**文件：**
- 修改：`backend/src/yitu/platform/outbox.py`
- 新建：`backend/tests/platform/test_worker_recovery.py`

**接口：**
- `consume_once(session, event_id, handler) -> bool`
- `handler(payload, idempotency_key) -> Awaitable[None]`

- [ ] 只写 1 个并发失败测试：重复投递同一事件时，可观察业务副作用只能发生一次。
- [ ] 使用数据库行锁仲裁；已完成事件直接返回 `False`，首次成功消费返回 `True`。
- [ ] handler 与事件状态更新处于同一调用方事务，服务不得自行提交。
- [ ] 运行并发测试 3 次；三次均通过即可，不做 10 次循环。
- [ ] 提交：`功能：确保 Outbox 事件幂等消费`

#### Task 5.5：五次失败后进入死信

**文件：**
- 修改：`backend/src/yitu/platform/outbox.py`
- 修改：`backend/tests/platform/test_worker_recovery.py`

**接口：**
- `RetryPolicy.next_attempt(attempts, now, jitter) -> datetime`

- [ ] 只写 1 个失败测试：handler 连续失败 5 次后，事件状态变为 `dead`，并产生一条数据库死信记录。
- [ ] 每次 handler 失败使用嵌套事务回滚业务副作用，同时保留失败次数。
- [ ] 第 1–4 次失败设置指数退避与随机抖动；基础延迟 30 秒，最长 30 分钟，抖动范围 0–10%。
- [ ] 第 5 次失败保存最后错误和处理建议，不再自动投递。
- [ ] 运行聚焦测试并确认通过。
- [ ] 提交：`功能：新增异步任务重试与死信处理`

#### Task 5.6：管理员安全重放死信

**文件：**
- 修改：`backend/src/yitu/platform/outbox.py`
- 修改：`backend/tests/platform/test_worker_recovery.py`

**接口：**
- `DeadLetterService(session, clock).replay(dead_letter_id) -> UUID`

- [ ] 只写 1 个失败测试：重放后原 Outbox 事件恢复为 `pending`，原 `idempotency_key` 保持不变，死信记录写入 `replayed_at`。
- [ ] 重放同一死信第二次时返回明确冲突，不重复创建事件。
- [ ] 运行聚焦测试并确认通过。
- [ ] 提交：`功能：支持安全重放死信任务`

#### Task 5.7：Celery 与 Redis Worker 接线

**文件：**
- 新建：`backend/src/yitu/platform/tasks.py`
- 新建：`backend/src/yitu/worker.py`
- 修改：`backend/src/yitu/platform/config.py`
- 修改：`backend/pyproject.toml`
- 修改：`backend/uv.lock`

**接口：**
- Celery 应用：`yitu.worker.celery_app`
- 任务：`relay_outbox`、`consume_outbox_event(event_id)`

- [ ] 新增 `YITU_REDIS_URL` 配置；Redis 只作为 Celery broker/backend，可靠状态继续保存在 PostgreSQL。
- [ ] `relay_outbox` 调用 `relay_pending_events()`；`consume_outbox_event` 调用 `consume_once()`。
- [ ] 不为 Celery 框架编写单元测试；运行导入检查：`uv run python -c "from yitu.worker import celery_app; print(celery_app.main)"`。
- [ ] 运行 Task 5 的最多 5 个核心行为测试，再运行一次 Ruff、mypy 和全量 pytest。
- [ ] 提交：`功能：接入 Celery 与 Redis 后台任务`

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
