<div align="center">

# 驿途 Yitu · 有真实履约约束的 AI 智能物流平台

**一句话下单，系统替你跑通计价、下单、路由、轨迹、取件的完整物流履约。**

不是「套个聊天框」的 Demo——AI 的每一个动作都受**状态机、业务规则和人工授权**约束，
生成的单据会真实驱动计价、路由、标签、轨迹和售后全流程。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](backend/pyproject.toml)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4%2B-1c394d)](backend/pyproject.toml)
[![Vue](https://img.shields.io/badge/Vue-3.5%2B-42b883)](frontend/package.json)

</div>

---

## ✨ 项目亮点

大多数「AI + 业务」项目止步于「能对话」。驿途把 AI 深度嵌进真实物流履约链路，几个值得看的工程点：

- **🧠 LangGraph 双层 Agent 编排**：主图（会话 / 检索 / 路由决策）+ 寄件子图（信息收集 → 计价 → 授权 → 建单），用端口-适配器架构隔离 LLM 与业务，确定性规则（计价 / 授权 / 建单）在适配层裁决，LangGraph 只负责控制流。
- **🔐 HITL 授权令牌（不是普通确认按钮）**：敏感动作走 **持久化授权令牌**（状态 `已创建→已授权/已拒绝/已过期`，幂等 TTL、可审计），AI 拿到令牌才提交建单，杜绝「模型说能下单就下单」。
- **🚚 状态机驱动的真实履约**：订单 / 运单 / 包裹 / 路由 / 取件码 / 异常件全链路状态流转，非法迁移直接拒绝；AI 建的单和人工建的单走**同一套**履约引擎。
- **📚 双路 RAG 混合检索**：知识库按「业务规则 / SOP / 区域政策」类型分域，向量召回 + 关键词召回 + RRF 融合 + Rerank 精排，命中策略可观测、可评测。
- **🛡️ 生产级可靠性**：Celery 异步任务 + Redis 队列、Outbox 事件可靠投递、死信队列与重放、幂等计费、审计日志、全链路追踪。
- **💬 流式 SSE 交互**：AI 回复逐字流式输出，思考过程、工具调用、确认卡片实时推送。

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| **Agent 编排** | LangGraph 0.4+（双层 ReAct 图、`interrupt()` 原生 HITL、Postgres checkpointer） |
| **后端框架** | FastAPI 0.115+、Pydantic v2、SQLAlchemy 2.0（async）、Alembic |
| **异步任务** | Celery 5.4 + Redis（PDF 解析、嵌入、事件消费，含 beat 定时） |
| **数据存储** | PostgreSQL 16 + **pgvector**（向量库）、Redis 7、MinIO / S3（对象存储） |
| **AI 能力** | OpenAI 兼容协议（DeepSeek 等）对话模型、阿里云百炼 Embedding、MinerU PDF 解析、可选 Rerank |
| **前端** | Vue 3.5 + TypeScript 5.7 + Vite 6 + Element Plus 2.9 + Axios |
| **部署** | Docker Compose（本地 & 生产模板）、Nginx（反代 + SSE）、uvicorn 多 worker |

---

## 🚀 快速开始

### 环境要求

- Docker Desktop（含 Docker Compose 插件）
- Node.js 22 + Python 3.11（仅本地非容器开发前端 / 跑测试时需要）

### 1. 克隆并配置环境变量

```bash
git clone https://github.com/<your-name>/yitu-logistics.git
cd yitu-logistics
cp .env.example .env
```

编辑 `.env`，至少填入对话模型与 Embedding 的 API Key（本地可先用 compose 自带的 PostgreSQL / Redis / MinIO）：

```ini
YITU_AGENT_MODEL_PROVIDER=openai_compatible
YITU_AGENT_MODEL_BASE_URL=https://api.deepseek.com/v1
YITU_AGENT_MODEL_API_KEY=sk-xxx
YITU_AGENT_MODEL_NAME=deepseek-chat

YITU_EMBEDDING_PROVIDER=qwen
YITU_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
YITU_EMBEDDING_API_KEY=sk-xxx
```

> 不想配外部 AI 也能启动——对话 / 嵌入会回退到本地桩，可体验 UI 与履约流程，但 AI 回答和语义检索为占位效果。

### 2. 一键启动基础设施 + 后端

```bash
docker compose up -d --build
```

该命令会启动 PostgreSQL（pgvector）、Redis、MinIO、FastAPI 后端，并**自动执行数据库迁移与种子数据**。

| 服务 | 地址 | 说明 |
|------|------|------|
| API 后端 | http://localhost:8000 | 健康检查 `/api/v1/health`，Swagger 文档 `/docs` |
| MinIO 控制台 | http://localhost:9001 | 本地对象存储（账号见 `.env`） |
| PostgreSQL | localhost:55433 | 仅本地开发映射 |
| Redis | localhost:6379 | 仅本地开发映射 |

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 ，Vite 已配置 `/api` 代理到后端 8000 端口。

### 4. 体验

- **演示账号**：`demo` / `YituDemo2026!`（管理员角色，可上传知识库 PDF、查看全量运单）
- 试试对话下单：
  - 「帮我寄一个 2 公斤的文件到北京朝阳，明天上午能到吗？」
  - AI 会收集信息 → 报价 → 推送**确认卡片** → 你点确认（授权令牌）→ 真实建单并返回运单号
- 用运单号查轨迹、发起取消 / 改派 / 售后，观察状态机约束。

---

## 📂 目录结构

```
yitu/
├── backend/
│   ├── src/yitu/
│   │   ├── agent/            # LangGraph 双层图、节点、状态、端口/适配器、工具
│   │   │   ├── workflow/     # 主图 + 寄件子图定义、路由、状态契约
│   │   │   ├── ports/        # 端口协议（Model/Knowledge/Workflow/...）
│   │   │   ├── adapters/     # 适配器实现（LLM、RAG、工作流裁决）
│   │   │   └── tools/        # Agent 可调用工具（计价、草稿、身份、知识）
│   │   ├── shipments/        # 运单 / 包裹 / 取件码 / 末次 Mile 凭证
│   │   ├── pricing/ labels/ dispatch/ tracking/ sla/   # 计价、标签、路由、轨迹、SLA
│   │   ├── payments/ returns/ stations/ regions/ addresses/
│   │   ├── knowledge/        # 知识库、PDF 解析、向量检索
│   │   ├── identity/ notifications/ demo/
│   │   ├── platform/         # 配置、DB 会话、中间件
│   │   ├── worker.py         # Celery 应用
│   │   └── main.py           # FastAPI 应用工厂
│   ├── migrations/           # Alembic 迁移
│   ├── tests/ evals/         # 单元测试 / Agent 评测
│   └── Dockerfile
├── frontend/
│   └── src/                  # Vue3 + TS 页面、API 封装、SSE 流式
├── deploy/                   # 生产部署模板（compose、Nginx、Dockerfile、env 样例）
├── docs/                     # 设计文档与技术资料
└── compose.yaml              # 本地开发编排
```

---

## 📚 文档索引

| 文档 | 内容 |
|------|------|
| [技术亮点](docs/technical-highlights.md) | 核心技术卖点与工程决策梳理 |
| [LangGraph 流程](docs/langgraph-flow.md) | 双层 Agent 图的节点、边与中断恢复 |
| [RAG 架构](docs/agent-rag-architecture.md) / [知识库 RAG](docs/knowledge-rag.md) | 双路混合检索、重排、评测设计 |
| [业务规则](docs/business/README.md) | [计价规则](docs/business/pricing-rules.md) · [SLA 规则](docs/business/sla-rules.md) |
| [产品需求](docs/prd/yitu-smart-logistics-prd.md) | 完整 PRD |
| [API 契约](docs/api/frontend-api-contract.md) / [API 指南](docs/api/frontend-api-guide.md) | 前后端接口约定 |
| [知识库样例](docs/knowledge/yitu-logistics-rules.md) | 灌入 RAG 的物流规则语料 |
| [**开源发布与部署上线**](docs/open-source-and-deployment.md) | 推送 GitHub/Gitee、生产部署、HTTPS、验收清单、上云 |

---

## ☁️ 部署上线

生产环境（Nginx + FastAPI + PostgreSQL + Redis + Celery，对象存储用腾讯云 COS）已提供模板：

```bash
cp deploy/.env.production.example deploy/.env.production   # 填入真实密钥
docker compose -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production up -d --build
```

完整步骤、HTTPS 证书、安全清单、数据库备份、K8s 演进路径见 **[部署上线指南](docs/open-source-and-deployment.md)**。

> ⚠️ 生产部署**必须**覆盖 `YITU_JWT_SECRET`、`YITU_PICKUP_CODE_PEPPER`（`openssl rand -hex 32` 生成）并设置 `YITU_APP_PROFILE=production`，否则会使用源码中的开发默认值。

---

## 🧪 开发与测试

```bash
# 后端测试（backend/ 目录，项目使用 uv 管理依赖）
cd backend
uv sync                 # 安装含 dev 组（pytest / ruff / mypy）的全部依赖
uv run pytest           # 单元测试
uv run ruff check .     # 代码风格
uv run mypy src         # 类型检查

# Agent 评测（图结构 & 隐私脱敏用例）
uv run python -m evals.run

# 前端类型检查 / 构建
cd frontend && npm run build
```

---

## 🤝 贡献

欢迎 Issue 与 PR！提交前请：

- 代码注释与 commit message 使用中文；
- 后端通过 `ruff` / `mypy` 检查与 `pytest`；
- 涉及 Agent 行为变更时，补充 / 更新 `backend/evals` 评测用例。

---

## 📄 License

[MIT](LICENSE) © 2026 yangshiqi
