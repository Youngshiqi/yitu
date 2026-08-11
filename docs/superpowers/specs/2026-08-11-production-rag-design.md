# 生产级 RAG 设计

## 目标

把当前开发占位实现替换为可上线链路：腾讯 COS 保存原始文件和解析产物，MinerU 云 API 异步解析，Qwen `qwen3.7-text-embedding` 生成向量，PostgreSQL pgvector 执行混合检索。只有审核发布后的知识版本可被检索。

## 数据流

1. 管理员上传 PDF，API 校验后写入私有 COS，并保存文档元数据。
2. Worker 为 COS 对象生成短时预签名 URL，调用 MinerU `POST /api/v4/extract/task`。
3. Worker 持久化 `task_id`，轮询 `GET /api/v4/extract/task/{task_id}`；完成后下载 `full_zip_url`。
4. Worker 安全解压结果，读取 `full.md`，将 Markdown、结构化结果、表格和图片产物写回 COS。
5. 切片器保留标题、表格语义、页码和来源信息，批量调用 Qwen OpenAI 兼容 Embedding API。
6. 向量写入 pgvector；审核发布后，关键词与向量检索共同参与排序并返回证据引用。

## 模块边界

- `BlobStore`：负责 COS 对象上传、下载、删除和短时预签名 URL，不泄露密钥。
- `MinerUClient`：负责任务提交、状态查询和结果下载，不访问数据库。
- `DocumentParser`：把 MinerU 产物转换为统一解析结果；PyMuPDF 只作为降级方案。
- `EmbeddingProvider`：批量生成向量并校验维度；Qwen 是生产实现，确定性向量只用于测试。
- `KnowledgeIndexer`：切片、版本化、写入 pgvector，禁止混用不同模型或维度。
- `KnowledgeRetriever`：只查询已发布且生效的版本，融合关键词和向量分数。

## 状态与恢复

文档状态保持显式转换：

```text
UPLOADED -> QUEUED -> PARSING -> REVIEW_REQUIRED -> PUBLISHED
                         |-> PARSE_FAILED
```

数据库保存 MinerU `task_id`、解析器版本、重试次数、最后错误、产物对象键、Embedding 模型和维度。Worker 重启后可继续轮询未完成任务。超时、网络错误和上游 5xx 使用退避重试；非法文件、解压路径穿越和永久业务错误不重试。

## 安全

- COS Bucket 保持私有，MinerU 只接收短时预签名 URL。
- COS、MinerU 和 DashScope 密钥只从 `.env` 或生产密钥管理服务读取。
- MinerU 压缩包限制下载大小、文件数量和解压后总大小，并拒绝路径穿越。
- 日志、错误响应和审计记录不得包含密钥、签名 URL 或完整文档内容。

## 小任务

1. 扩展 `BlobStore`：增加 COS 预签名 URL、通用内容类型和解析产物对象键。
2. 实现 `MinerUClient`：提交、轮询、下载和稳定错误映射。
3. 扩展持久化模型：记录 MinerU 任务、解析产物和恢复信息，新增 Alembic 迁移。
4. 重构解析 Worker：异步提交、轮询恢复、安全解压、产物回存和 PyMuPDF 降级。
5. 实现 Qwen Embedding Provider：OpenAI 兼容批量调用、维度探测、限流与重试。
6. 启用 pgvector：向量列、模型版本、维度约束和向量索引迁移。
7. 升级切片与索引：标题、表格、页码、版本隔离和批量写入。
8. 升级混合检索：数据库向量相似度、关键词检索、发布和生效时间过滤。
9. 补关键验证：COS、MinerU、Qwen 冒烟测试，Worker 恢复和 HTTP 全链路验收。
10. 更新中文配置、运维和故障恢复文档，执行阶段四最终收口。

## 验收标准

- 真实 PDF 经 COS、MinerU、Qwen 和 pgvector 完成上传到引用的闭环。
- 扫描件和表格样例可以生成可读 Markdown，并保留可核验来源。
- 未发布、已停用或超出生效期的内容不可检索。
- Worker 重启后任务可恢复，重复投递不会生成重复版本。
- `ruff`、`mypy`、相关 pytest、迁移和真实 HTTP 验收通过。
