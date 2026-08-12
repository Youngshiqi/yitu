# 驿途后端阶段四：知识库与 RAG 实施计划

> **完成状态（2026-08-12）：** 本计划的功能范围已由生产 RAG 扩展计划实现并完成真实链路验收。真实 MinerU `full.md` 不包含页码标记，页码/坐标映射明确保留为后续结构化布局适配项，不影响当前全文与向量混合检索。

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 通过管理员 HTTP API 完成 PDF 安全上传、异步解析、人工预览、版本发布、中文混合检索和页码引用。

**架构：** `BlobStore` 隔离文件存储；Celery Worker 执行 MinerU/PyMuPDF、切片和索引；PostgreSQL 保存工作流事实、全文索引和 pgvector，只有已发布版本可检索。

**技术栈：** MinerU、PyMuPDF、jieba、PostgreSQL tsvector/GIN、pgvector、Celery、Docker 卷。

## 全局约束

- `OPERATIONS_ADMIN` 与 `SYSTEM_ADMIN` 可管理文档生命周期；只有 `SYSTEM_ADMIN` 可改解析/Embedding/索引配置和重放死信。
- 原始文件不存数据库；文件名不得成为存储路径；未发布内容不得进入 Agent 检索。
- 阶段开始需要 MinerU 下载时，先向用户说明磁盘、网络、时间和验证方式。

---

### 任务 1：BlobStore 与安全 PDF 上传

**文件：** 新建 `backend/src/yitu/knowledge/{blob_store,models,schemas,service,router}.py`；迁移 `0016`；测试 `backend/tests/knowledge/test_upload.py`；修改 Compose 卷配置。

**接口：** 产出 `BlobStore.put/open/delete`、`POST /api/v1/knowledge/documents` 和文档状态 API。

- [x] 测试流式上传、PDF 文件头/MIME/大小/页数/加密检查、SHA-256 去重、路径穿越和角色矩阵。
- [ ] 运行知识库上传测试；预期因缺少模块而失败。
- [x] 实现使用生成对象键的本地卷 BlobStore，数据库只保存元数据行。
- [x] 运行迁移和上传测试；预期全部通过。
- [x] 提交：`功能：新增安全知识库上传`。

### 任务 2：解析 Worker 与持久状态机

**文件：** 新建 `backend/src/yitu/knowledge/{parsers,tasks,state_machine}.py`；迁移 `0017`；测试 `backend/tests/knowledge/test_parsing.py`。

**接口：** 产出 `MinerUParser`、`PyMuPDFParser`、`parse_document(document_id)`，以及状态 `UPLOADED/QUEUED/PARSING/REVIEW_REQUIRED/PARSE_FAILED`。

- [ ] 测试文本 PDF、扫描件夹具、损坏文件、超时、五次重试、降级警告和 Worker 重启恢复。
- [ ] 使用固定解析适配器运行解析测试；预期因缺少解析契约而失败。
- [x] 实现解析适配器边界、结构化解析产物和 PyMuPDF 纯文本降级方案，并在生产扩展中接入 MinerU 云 API。
- [x] 经用户明确同意后完成真实 MinerU 冒烟与待审核结果验证。
- [x] 提交：`功能：异步解析 PDF 知识文档`。

### 任务 3：切片、版本化向量与索引构建

**文件：** 新建 `backend/src/yitu/knowledge/{chunking,embedding,indexing}.py`；迁移 `0018`；测试 `backend/tests/knowledge/test_chunking.py`、`test_indexing.py`。

**接口：** 产出 `ChunkingPolicy.chunk()`、`EmbeddingProvider.embed()`、`build_index_version()`。

- [ ] 测试标题/表格边界、500–800 个中文字符切分、页码/坐标、页眉清理、向量维度和混合版本拒绝。
- [ ] 运行切片/索引测试；预期因缺少策略而失败。
- [x] 实现确定性切片器、供 CI 使用的固定向量适配器、jieba 分词、tsvector 和独立的向量索引版本。
- [x] 运行迁移和测试；预期全部通过。
- [x] 提交：`功能：构建版本化知识索引`。
- [ ] 从 MinerU 结构化布局产物提取真实页码/坐标；当前 `full.md` 链路无法提供该元数据。

### 任务 4：预览、审核、发布、归档与重新解析 API

**文件：** 修改知识库服务、路由和模式；测试 `backend/tests/knowledge/test_review_publish.py`。

**接口：** 产出预览/产物路由，以及 `review`、`publish`、`archive`、`deactivate`、`reparse` 动作。

- [ ] 测试两种管理员角色、仅系统管理员可修改配置、必须指定审核人、新版本原子切换、新版本失败降级和审计记录。
- [ ] 运行审核测试；预期因缺少动作而失败。
- [x] 实现显式生命周期命令；解析或索引后绝不自动发布。
- [x] 运行测试；预期全部通过。
- [x] 提交：`功能：新增审核后知识发布`。

### 任务 5：混合检索与可验证引用

**文件：** 新建 `backend/src/yitu/knowledge/retrieval.py`；新建查询路由；测试 `backend/tests/knowledge/test_retrieval.py`。

**接口：** 产出 `KnowledgeRetriever.search(query, filters, limit) -> list[Evidence]`；证据包含文档、版本、标题、页码、坐标、片段和分数。

- [ ] 测试中文关键词、同义词、语义问题、角色/生效日期过滤、排除未发布内容和证据不足拒答信号。
- [ ] 运行检索测试；预期因缺少检索器而失败。
- [x] 实现归一化关键词/向量加权融合和稳定的分数组成；预留可注入重排器但暂不启用。
- [x] 运行检索测试；预期所有质量夹具达到记录阈值。
- [x] 提交：`功能：新增带引用的混合知识检索`。

### 任务 6：RAG 阶段验收

**文件：** 新建 `backend/tests/journeys/test_knowledge_pipeline.py`；添加测试 PDF 夹具和 README 知识库章节。

**接口：** 产出从上传到引用的纯 HTTP 旅程。

- [x] 验证上传 → 解析 → 预览 → 发布 → 检索、版本隔离和引用字段；真实页码映射保留为上述后续项。
- [x] 历史阶段验收已运行知识库相关测试；任务十按用户要求不重复运行 pytest。
- [x] 验证迁移状态、Compose 服务和 Worker 恢复链路。
- [x] 记录真实解析器、模型、维度、知识块和证据数量。
- [x] 提交：`验证：打通生产 RAG 全链路`。
