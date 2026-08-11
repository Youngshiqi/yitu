# 生产级 RAG 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用腾讯 COS、MinerU 云 API、Qwen Embedding 和 PostgreSQL pgvector 构建可上线的知识库解析、索引和检索链路。

**Architecture:** API 将私有 PDF 写入 COS，Worker 使用短时签名 URL 提交 MinerU 异步任务并回存解析产物，再调用 Qwen OpenAI 兼容接口生成向量。PostgreSQL 保存工作流状态、版本化知识块、全文索引和 pgvector，检索只读取已发布且生效的版本。

**Tech Stack:** FastAPI、Celery、PostgreSQL 16、pgvector、SQLAlchemy、boto3、httpx、OpenAI 兼容 Embedding API、MinerU v4 API。

## Global Constraints

- COS Bucket 必须保持私有，MinerU 只接收短时预签名 URL。
- COS、MinerU 和 DashScope 密钥只从环境变量读取，不写日志、不进入 Git。
- 生产 Embedding 模型固定为 `qwen3.7-text-embedding`；实际维度由首次响应探测并持久化。
- 只有 `PUBLISHED` 且处于生效期的知识版本可以被检索。
- 新增关键代码使用简体中文注释或 docstring，标识符和错误码使用英文。
- 每个任务只运行相关测试；最终收口运行全量 Ruff、mypy、pytest、迁移和真实 HTTP 验收。

---

### Task 1: COS 预签名 URL 与通用产物存储

**Files:**
- Modify: `backend/src/yitu/knowledge/blob_store.py`
- Test: `backend/tests/knowledge/test_blob_store.py`

**Interfaces:**
- Produces: `BlobStore.put(key, data, content_type)`, `BlobStore.presign_get(key, expires_seconds) -> str`
- Consumes: `Settings.knowledge_s3_*`

- [ ] 增加最小单元测试，验证对象键、内容类型、签名有效期和本地实现不支持签名时的稳定异常。
- [ ] 扩展 `BlobStore` 协议；`S3BlobStore` 使用 `generate_presigned_url("get_object", ...)`，默认有效期 900 秒。
- [ ] 让 PDF、Markdown、JSON、ZIP、图片共用 `put`，调用方显式传递 MIME。
- [ ] 运行 `uv run pytest tests/knowledge/test_blob_store.py -q`、Ruff、mypy。
- [ ] 提交 `功能：扩展 COS 知识产物存储能力`。

### Task 2: MinerU v4 HTTP 客户端

**Files:**
- Create: `backend/src/yitu/knowledge/mineru_client.py`
- Modify: `backend/pyproject.toml`, `backend/uv.lock`
- Test: `backend/tests/knowledge/test_mineru_client.py`

**Interfaces:**
- Produces: `MinerUClient.submit(source_url) -> str`, `MinerUClient.get_task(task_id) -> MinerUTask`, `MinerUClient.download_result(url) -> bytes`
- Consumes: `Settings.mineru_base_url`, `mineru_token`, `mineru_model_version`

- [ ] 用 `httpx.MockTransport` 覆盖提交成功、处理中、完成、限流、5xx 和永久错误。
- [ ] 实现 Bearer 认证、`POST /api/v4/extract/task`、`GET /api/v4/extract/task/{task_id}` 和 `full_zip_url` 下载。
- [ ] 定义稳定异常 `MinerURetryableError`、`MinerUPermanentError`，异常中不包含 Token 或签名 URL。
- [ ] 运行相关测试、Ruff、mypy并提交 `功能：接入 MinerU 云端解析 API`。

### Task 3: MinerU 工作流持久化

**Files:**
- Modify: `backend/src/yitu/knowledge/models.py`, `schemas.py`
- Create: `backend/migrations/versions/0024_add_mineru_workflow.py`
- Test: `backend/tests/knowledge/test_mineru_models.py`

**Interfaces:**
- Produces: `mineru_task_id`, `source_artifact_key`, `markdown_artifact_key`, `result_archive_key`, `parse_started_at`, `parse_finished_at`

- [ ] 增加模型和迁移断言，要求 MinerU 任务 ID 可恢复且产物对象键可追踪。
- [ ] 添加字段、索引和响应字段；历史迁移保持不变。
- [ ] 运行 `alembic heads`、相关测试、Ruff、mypy并提交 `功能：持久化 MinerU 解析工作流`。

### Task 4: 安全解析 Worker 与恢复

**Files:**
- Modify: `backend/src/yitu/knowledge/tasks.py`, `parsers.py`, `state_machine.py`
- Create: `backend/src/yitu/knowledge/artifacts.py`
- Test: `backend/tests/knowledge/test_mineru_worker.py`

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: `submit_mineru_document(document_id)`, `poll_mineru_document(document_id)`, `extract_mineru_archive(data)`

- [ ] 覆盖重复投递、Worker 重启、处理中重试、失败状态和成功产物回存。
- [ ] 安全解压 ZIP：限制 200MB、2000 个文件、拒绝绝对路径和 `..`，读取 `full.md`。
- [ ] 提交任务时生成 15 分钟 COS URL；持久化 task_id 后独立轮询，完成后回存 ZIP 与 Markdown。
- [ ] 永久错误进入 `PARSE_FAILED`，临时错误使用 Celery 退避重试；日志仅记录 document_id/task_id。
- [ ] 运行相关测试并提交 `功能：实现可恢复的 MinerU 解析 Worker`。

### Task 5: Qwen Embedding Provider

**Files:**
- Modify: `backend/src/yitu/knowledge/embedding.py`, `backend/pyproject.toml`, `backend/uv.lock`
- Test: `backend/tests/knowledge/test_qwen_embedding.py`

**Interfaces:**
- Produces: `QwenEmbeddingProvider.embed(texts) -> list[list[float]]`, `get_embedding_provider()`
- Consumes: `Settings.embedding_*`

- [ ] 使用 OpenAI 兼容 MockTransport 覆盖批量输入、顺序保持、维度探测、429、5xx、空响应和维度漂移。
- [ ] 实现批次大小 32、超时 60 秒、重试后稳定异常；生产配置选择 Qwen，测试配置选择确定性 Provider。
- [ ] 响应向量归一化并记录模型名与维度，不记录文本内容。
- [ ] 运行相关测试并提交 `功能：接入 Qwen 文本向量模型`。

### Task 6: pgvector 模型与迁移

**Files:**
- Modify: `backend/src/yitu/knowledge/models.py`, `backend/pyproject.toml`, `backend/uv.lock`
- Create: `backend/migrations/versions/0025_enable_knowledge_pgvector.py`
- Test: `backend/tests/knowledge/test_vector_migration.py`

**Interfaces:**
- Produces: pgvector `embedding` 列、`embedding_model`、`embedding_dimension`、向量索引

- [ ] 增加迁移测试，验证 `CREATE EXTENSION vector`、JSONB 旧向量清理策略和新列约束。
- [ ] 使用 `pgvector` SQLAlchemy 类型；维度按 Qwen 首次探测结果固定，维度不一致拒绝构建索引。
- [ ] 创建适合当前规模的 HNSW cosine 索引，保留关键词 GIN 索引。
- [ ] 运行迁移往返、相关测试、Ruff、mypy并提交 `功能：启用 pgvector 知识向量索引`。

### Task 7: 生产切片与版本化索引

**Files:**
- Modify: `backend/src/yitu/knowledge/chunking.py`, `indexing.py`, `models.py`
- Test: `backend/tests/knowledge/test_production_indexing.py`

**Interfaces:**
- Consumes: MinerU Markdown、Qwen Provider、pgvector
- Produces: 标题、表格、页码、内容和向量完整的 `KnowledgeChunk`

- [ ] 覆盖标题边界、Markdown 表格、页码标记、800 字符上限、100 字符重叠和版本隔离。
- [ ] 解析 MinerU Markdown 标题与表格，生成确定性 chunk_id；按 32 条批量生成并写入向量。
- [ ] 索引构建失败时保留上一可用版本，不发布半成品。
- [ ] 运行相关测试并提交 `功能：构建生产级版本化知识索引`。

### Task 8: PostgreSQL 混合检索

**Files:**
- Modify: `backend/src/yitu/knowledge/retrieval.py`, `retrieval_schemas.py`
- Test: `backend/tests/knowledge/test_production_retrieval.py`

**Interfaces:**
- Produces: `KnowledgeRetriever.search(query, category, limit) -> list[Evidence]`

- [ ] 覆盖中文查询、分类、生效时间、未发布排除、停用排除和证据页码。
- [ ] 在 PostgreSQL 中计算 cosine distance 与全文排名，归一化后按关键词 0.55、向量 0.45 融合。
- [ ] 限制候选集和最终结果数，分数相同时使用稳定顺序。
- [ ] 运行相关测试并提交 `功能：实现 pgvector 混合知识检索`。

### Task 9: 真实服务冒烟与 HTTP 链路

**Files:**
- Create: `backend/tests/journeys/test_production_knowledge_pipeline.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: Tasks 1-8
- Produces: 可重复的上传到证据验收路径

- [ ] 增加固定适配器的自动化旅程：上传、MinerU 完成、审核、发布、检索。
- [ ] 使用本机 `.env` 单独运行 COS put/get/delete、MinerU 提交/轮询、Qwen 维度探测冒烟脚本；不打印密钥和签名 URL。
- [ ] 使用真实 Compose 执行完整 HTTP 流程，并记录文档 ID、解析状态、模型、维度和证据数量。
- [ ] 提交 `测试：验证生产级 RAG 全链路`。

### Task 10: 生产 RAG 收口

**Files:**
- Modify: `docs/knowledge-rag.md`, `.env.example`, `README.md`
- Modify: `docs/superpowers/plans/2026-08-09-backend-phase-4-knowledge-rag.md`

**Interfaces:**
- Produces: 配置、运行、轮换密钥、重建索引和故障恢复说明

- [ ] 用中文记录 COS、MinerU、Qwen、pgvector 配置与密钥轮换步骤，示例只用空值。
- [ ] 记录解析失败、Worker 重启、模型维度变化和索引重建流程。
- [ ] 运行 `uv run ruff check .`、`uv run mypy src`、相关 pytest、`alembic upgrade head` 和 `docker compose config`。
- [ ] 确认 Git 工作区无密钥、签名 URL、PDF 或解析产物，提交 `文档：完成生产级 RAG 阶段验收`。
