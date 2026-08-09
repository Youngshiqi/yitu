# 驿途后端阶段一：工程基础实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 建立可通过 Docker Compose 运行、具备数据库迁移、统一时间、错误、幂等、审计和异步任务骨架的 FastAPI 后端。

**架构：** `platform` 提供跨模块基础能力，业务模块只能依赖这些稳定接口。PostgreSQL 是事实源，Redis 只作为 Celery broker/backend，API 与 Worker 使用相同配置和数据库模型。

**技术栈：** Python 3.11、uv、FastAPI、Pydantic v2、SQLAlchemy 2 async、Alembic、PostgreSQL 16 + pgvector、Redis 7、Celery、pytest、HTTPX、Ruff、mypy、Docker Compose。

## 全局约束

- 遵守 `.CLAUDE` 与完整后端设计；业务时间固定为 `Asia/Shanghai`。
- 包布局使用 `backend/src/yitu`，测试使用真实 PostgreSQL。
- 新增注释与 docstring 使用简体中文。
- 本阶段不实现具体物流业务和前端。

---

### 任务 1：Python 工程与健康检查 API

**文件：**
- 新建：`backend/pyproject.toml`
- 新建：`backend/src/yitu/__init__.py`
- 新建：`backend/src/yitu/main.py`
- 新建：`backend/tests/api/test_health.py`
- 新建：`backend/tests/conftest.py`

**接口：**
- 产出：`create_app() -> FastAPI`、`GET /api/v1/health -> HealthResponse`

- [ ] **步骤 1：编写失败的 HTTP 测试**

```python
async def test_health_reports_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **步骤 2：确认测试处于红灯状态**

运行：`cd backend; uv run pytest tests/api/test_health.py -q`
预期：由于 `yitu.main` 不存在，测试收集失败。

- [ ] **步骤 3：添加最小包结构与应用工厂**

配置运行时与开发依赖、pytest 异步模式、Ruff 和 mypy。实现 `HealthResponse`、`create_app()` 和带版本号的健康检查路由。

- [ ] **步骤 4：确认测试处于绿灯状态**

运行：`cd backend; uv run ruff check .; uv run mypy src; uv run pytest tests/api/test_health.py -q`
预期：所有命令退出码为 0，且一个测试通过。

- [ ] **步骤 5：提交**

```bash
git add backend
git commit -m "工程：搭建 FastAPI 后端基础结构"
```

### 任务 2：类型化配置、时钟与错误契约

**文件：**
- 新建：`backend/src/yitu/platform/config.py`
- 新建：`backend/src/yitu/platform/clock.py`
- 新建：`backend/src/yitu/platform/errors.py`
- 新建：`backend/src/yitu/platform/schemas.py`
- 新建：`backend/tests/platform/test_clock.py`
- 新建：`backend/tests/api/test_errors.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：`Settings`、`get_settings()`、`Clock.now()`、`to_business_timezone()`、`AppError`、`ErrorResponse`

- [ ] **步骤 1：编写失败的契约测试**

测试 UTC 零点能够转换为 `2026-08-09T08:00:00+08:00`、拒绝无时区时间，并验证 `AppError("INVALID_INPUT", ..., 422)` 返回 `code`、中文 `message`、`request_id` 和 `details`。

- [ ] **步骤 2：确认测试处于红灯状态**

运行：`cd backend; uv run pytest tests/platform/test_clock.py tests/api/test_errors.py -q`
预期：由于缺少平台模块，导入失败。

- [ ] **步骤 3：实现共享契约**

使用 `ZoneInfo("Asia/Shanghai")`、带缓存的 Pydantic Settings 工厂、支持时区的响应基类、请求 ID 中间件，以及处理 `AppError` 的 FastAPI 异常处理器。

- [ ] **步骤 4：确认测试处于绿灯状态**

运行：`cd backend; uv run pytest tests/platform/test_clock.py tests/api/test_errors.py -q`
预期：所有测试通过。

- [ ] **步骤 5：提交**

```bash
git add backend/src/yitu/platform backend/src/yitu/main.py backend/tests
git commit -m "功能：新增共享时间与错误契约"
```

### 任务 3：PostgreSQL、SQLAlchemy 与 Alembic

**文件：**
- 新建：`backend/src/yitu/platform/database.py`
- 新建：`backend/src/yitu/platform/models.py`
- 新建：`backend/alembic.ini`
- 新建：`backend/migrations/env.py`
- 新建：`backend/migrations/versions/0001_create_platform_tables.py`
- 新建：`backend/tests/platform/test_database.py`
- 修改：`backend/tests/conftest.py`

**接口：**
- 产出：`Base`、`SessionFactory`、`get_session()`、`transactional_session()`

- [ ] **步骤 1：编写 PostgreSQL 集成测试**

断言数据库连接报告 `Asia/Shanghai` 时区、`SELECT now()` 返回带时区时间、事务在异常时回滚，并确认 pgvector 扩展可用。

- [ ] **步骤 2：确认测试处于红灯状态**

运行：`cd backend; uv run pytest tests/platform/test_database.py -q`
预期：数据库导入或连接夹具失败。

- [ ] **步骤 3：实现数据库基础能力**

创建异步引擎和会话工厂，在连接时设置会话时区，共享同一个声明式 `Base`，并配置 Alembic 导入元数据。迁移 `0001` 启用 `vector`，并创建由迁移管理的平台元数据。

- [ ] **步骤 4：确认测试通过并验证迁移往返**

运行：`cd backend; uv run alembic upgrade head; uv run pytest tests/platform/test_database.py -q; uv run alembic downgrade base; uv run alembic upgrade head`
预期：每条命令退出码均为 0。

- [ ] **步骤 5：提交**

```bash
git add backend
git commit -m "功能：配置 PostgreSQL 持久化"
```

### 任务 4：幂等与审计基础

**文件：**
- 新建：`backend/src/yitu/platform/idempotency.py`
- 新建：`backend/src/yitu/platform/audit.py`
- 新建：`backend/migrations/versions/0002_create_idempotency_and_audit.py`
- 新建：`backend/tests/platform/test_idempotency.py`
- 新建：`backend/tests/platform/test_audit.py`

**接口：**
- 产出：`IdempotencyService.execute(scope, key, request_hash, operation)`、`AuditService.record(...)`

- [ ] **步骤 1：编写失败的重放与冲突测试**

验证相同键和哈希会重放已保存响应，相同键但不同哈希会抛出 `IDEMPOTENCY_KEY_REUSED`，并发执行只保存一个结果，并且不能通过服务更新审计记录。

- [ ] **步骤 2：确认测试处于红灯状态**

运行：`cd backend; uv run pytest tests/platform/test_idempotency.py tests/platform/test_audit.py -q`
预期：由于缺少服务和数据表而失败。

- [ ] **步骤 3：实现原子记录**

使用唯一 `(scope, key)` 约束、规范 JSON 的 SHA-256 请求哈希、响应状态与正文快照，以及只追加的审计记录；审计内容包含操作者、动作、资源、变更前后摘要、原因、请求 ID 和时间。

- [ ] **步骤 4：确认测试处于绿灯状态**

运行：`cd backend; uv run alembic upgrade head; uv run pytest tests/platform/test_idempotency.py tests/platform/test_audit.py -q`
预期：所有测试通过。

- [ ] **步骤 5：提交**

```bash
git add backend
git commit -m "功能：新增幂等与审计基础能力"
```

### 任务 5：可靠异步任务基础

任务 5 拆成 7 个可独立验收的小任务。整个任务 5 最多新增 5 个核心行为测试，不逐列测试数据库结构，也不测试 Celery 框架本身。

#### 任务 5.1：Outbox 与死信数据库迁移

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

#### 任务 5.2：事务内追加 Outbox 事件

**文件：**
- 新建：`backend/src/yitu/platform/outbox.py`
- 新建或修改：`backend/tests/platform/test_outbox.py`

**接口：**
- `OutboxService(session, clock).append(event_type, business_id, payload, idempotency_key) -> UUID`

- [ ] 只写 1 个失败测试：在同一事务写入业务探针和 Outbox 事件，随后主动抛错，验证二者一起回滚。
- [ ] 实现 `append()`；只执行插入，不自行 `commit`，初始状态为 `pending`、尝试次数为 `0`。
- [ ] 运行该聚焦测试并确认通过。
- [ ] 提交：`功能：支持事务内追加 Outbox 事件`

#### 任务 5.3：投递到期事件

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

#### 任务 5.4：幂等消费单个事件

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

#### 任务 5.5：五次失败后进入死信

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

#### 任务 5.6：管理员安全重放死信

**文件：**
- 修改：`backend/src/yitu/platform/outbox.py`
- 修改：`backend/tests/platform/test_worker_recovery.py`

**接口：**
- `DeadLetterService(session, clock).replay(dead_letter_id) -> UUID`

- [ ] 只写 1 个失败测试：重放后原 Outbox 事件恢复为 `pending`，原 `idempotency_key` 保持不变，死信记录写入 `replayed_at`。
- [ ] 重放同一死信第二次时返回明确冲突，不重复创建事件。
- [ ] 运行聚焦测试并确认通过。
- [ ] 提交：`功能：支持安全重放死信任务`

#### 任务 5.7：Celery 与 Redis Worker 接线

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
- [ ] 运行任务 5 的最多 5 个核心行为测试，再运行一次 Ruff、mypy 和全量 pytest。
- [ ] 提交：`功能：接入 Celery 与 Redis 后台任务`

### 任务 6：Docker Compose 与阶段验收

**文件：**
- 新建：`.env.example`
- 修改：`.gitignore`
- 新建：`.gitattributes`
- 新建：`compose.yaml`
- 新建：`backend/Dockerfile`
- 新建：`README.md`
- 新建：`CONTEXT.md`
- 新建：`backend/tests/api/test_readiness.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：Compose 服务 `db`、`redis`、`api`、`worker`；`GET /api/v1/readiness`

- [ ] **步骤 1：请用户启动 Docker Desktop**

说明如何打开 Docker Desktop，并等待引擎显示正在运行。使用 `docker info` 验证；引擎不可用时不得继续 Compose 检查。

- [ ] **步骤 2：编写就绪检查测试与容器定义**

就绪检查路由必须在限定超时时间内检查 PostgreSQL 和 Redis。Compose 使用带 pgvector 的 PostgreSQL 16、Redis 7、API 与 Worker 健康检查、命名卷，并且不得提交密钥。

- [ ] **步骤 3：构建并迁移**

运行：`docker compose up --build -d; docker compose exec api uv run alembic upgrade head`
预期：四个服务全部变为健康状态，迁移到达最新版本。

- [ ] **步骤 4：执行完整阶段验收**

运行：`cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`
运行：`docker compose ps; Invoke-RestMethod http://localhost:8000/api/v1/readiness`
预期：检查退出码为 0、测试通过、服务健康，且就绪检查返回 `{"status":"ready"}`。

- [ ] **步骤 5：提交**

```bash
git add .gitattributes .gitignore .env.example compose.yaml README.md CONTEXT.md backend
git commit -m "工程：交付可运行的后端基础"
```
