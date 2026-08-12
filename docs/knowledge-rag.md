# 知识库与生产 RAG

## 架构与数据位置

生产链路为：

```text
管理员上传 PDF
  -> 腾讯 COS 保存原始文件
  -> Celery Worker 向 MinerU 提交短时签名 URL
  -> MinerU Markdown 与结果 ZIP 回存 COS
  -> jieba 分词与生产切片
  -> Qwen Embedding 生成 1024 维向量
  -> PostgreSQL pgvector、GIN 保存索引
  -> 管理员审核发布
  -> 关键词 0.55 + 向量 0.45 混合检索
```

原始 PDF、MinerU Markdown 和结果 ZIP 位于 COS 私有桶；PostgreSQL 只保存工作流元数据、解析正文、知识块和向量。`backend/var/knowledge/inbox` 仅用于管理员上传前暂存文件，不是生产对象存储。

## 文档生命周期

```text
UPLOADED -> QUEUED -> PARSING -> REVIEW_REQUIRED -> PUBLISHED
                                  |                 |
                                  v                 v
                            PARSE_FAILED      ARCHIVED/DEACTIVATED
```

上传成功后 API 自动进入 `QUEUED` 并投递 Worker。解析和索引完成后停在 `REVIEW_REQUIRED`，必须由运营管理员或系统管理员审核并发布。只有 `PUBLISHED` 且处于生效时间范围内的文档参与检索。

## 生产配置

所有真实值只写入部署环境的 `.env` 或密钥管理服务，不写入 Git、日志或聊天记录。

| 配置 | 用途 |
| --- | --- |
| `YITU_KNOWLEDGE_STORAGE_BACKEND=s3` | 启用 S3 兼容对象存储 |
| `YITU_KNOWLEDGE_S3_ENDPOINT` | COS 地域 endpoint，不包含桶名 |
| `YITU_KNOWLEDGE_S3_BUCKET` | COS 私有桶名称 |
| `YITU_KNOWLEDGE_S3_REGION` | COS 地域，例如 `ap-guangzhou` |
| `YITU_KNOWLEDGE_S3_ACCESS_KEY` | CAM 子用户 SecretId |
| `YITU_KNOWLEDGE_S3_SECRET_KEY` | CAM 子用户 SecretKey |
| `YITU_MINERU_BASE_URL` | MinerU API 根地址 |
| `YITU_MINERU_TOKEN` | MinerU API Token |
| `YITU_MINERU_MODEL_VERSION` | MinerU 模型版本，当前为 `vlm` |
| `YITU_EMBEDDING_PROVIDER=qwen` | 启用百炼向量服务 |
| `YITU_EMBEDDING_BASE_URL` | 北京工作空间 OpenAI 兼容地址 |
| `YITU_EMBEDDING_API_KEY` | 阿里云百炼 API Key |
| `YITU_EMBEDDING_MODEL` | 当前为 `qwen3.7-text-embedding` |
| `YITU_EMBEDDING_DIMENSION=1024` | pgvector 固定维度 |

COS 客户端使用 virtual-hosted-style，并启用 `AES256` 服务端加密。MinerU 签名 URL 有效期为 15 分钟，认证头不会发送给产物 CDN。Qwen 单批最多发送 20 个知识块。

## 管理与检索 API

知识文档生命周期接口需要 `OPERATIONS_ADMIN` 或 `SYSTEM_ADMIN`：

```text
POST /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents/{document_id}
POST /api/v1/knowledge/documents/{document_id}/review
POST /api/v1/knowledge/documents/{document_id}/publish
POST /api/v1/knowledge/documents/{document_id}/archive
POST /api/v1/knowledge/documents/{document_id}/deactivate
POST /api/v1/knowledge/documents/{document_id}/reparse
```

已登录用户可检索已发布证据：

```text
GET /api/v1/knowledge/search?query=禁止寄递物品&category=prohibited-items&limit=5
```

证据包含文档、索引版本、标题、章节路径、内容类型、页码、正文片段和归一化分数。检索只读取每份文档的最新索引版本。

## 索引重建与恢复

### 解析失败

1. 查看文档 `status` 和 `error_message`，不要记录签名 URL 或原文。
2. 临时网络、限流和上游 5xx 由 Celery 自动退避重试。
3. 永久解析或向量错误进入 `PARSE_FAILED`。
4. 修复配置后调用 `POST /documents/{id}/reparse`，系统保留 COS 原始 PDF 并创建新解析任务。

### Worker 重启

MinerU `task_id` 持久化在 PostgreSQL。Worker 重启后重复提交同一文档时会恢复轮询，不会再次创建 MinerU 任务。已完成的 MinerU 产物可以重新执行轮询以恢复向量构建。

### 模型或维度变化

同一个 `vector(1024)` 列禁止混入其他维度。更换模型前必须：

1. 在隔离环境探测新模型维度。
2. 若维度仍为 1024，更新配置后对文档执行重新解析或专用重建任务。
3. 若维度变化，先新增迁移和新向量列或索引，不得直接修改线上列后混写。
4. 新版本完成质量检查后再发布，构建失败时保留上一可用版本。

### 密钥轮换

1. 在云厂商创建新密钥或 Token，保持旧密钥暂时有效。
2. 更新部署密钥存储并重建 API、Worker。
3. 用布尔配置摘要、COS 小对象、MinerU 状态查询和 Qwen 单条向量验证新密钥。
4. 确认服务健康后禁用旧密钥。
5. 若密钥曾进入聊天或日志，立即吊销，不只做常规轮换。

## 验收与限制

固定适配器旅程：

```powershell
cd backend
$env:PYTHONPATH='src'
uv run python scripts/production_knowledge_smoke.py
```

脚本使用本地临时 BlobStore、固定 MinerU 产物和确定性 1024 维向量，不调用外部服务，不打印密钥，并在结束后清理临时文档。

2026-08-12 已完成真实 Compose 验收：COS 上传、MinerU 解析、Qwen 向量化、管理员发布和混合检索均成功。验收文档生成 87 个知识块，检索返回 5 条证据。

当前 MinerU `full.md` 未携带页码标记，因此该真实文档证据页码为空。检索功能可用，但 PDF 页码跳转需要后续接入 MinerU 结构化布局产物，将页码和区块坐标映射到知识块。
