# 驿途后端整体实施路线图

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照各阶段计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 按六个可验收阶段完成驿途全部后端，冻结 OpenAPI 后再开始前端。

**架构：** FastAPI 模块化单体承载同步业务，PostgreSQL/pgvector 保存长期事实，Redis/Celery 处理异步任务，LangGraph 编排 Agent。各阶段只通过稳定应用服务协作，普通 API 与 Agent 工具不得复制领域规则。

**技术栈：** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL 16、pgvector、Redis 7、Celery、LangGraph、MinerU、PyMuPDF、pytest、HTTPX、Ruff、mypy、Docker Compose。

## 全局约束

- 遵守根目录 `.CLAUDE`、PRD 1.4 和 `docs/superpowers/specs/2026-08-09-backend-first-design.md`。
- 所有新增注释和 docstring 使用简体中文，标识符与错误码使用英文。
- 所有写接口校验 JWT、资源范围、当前状态和 `Idempotency-Key`。
- 金额使用整数分；时间统一为 `Asia/Shanghai`；长期事实只存 PostgreSQL。
- PostgreSQL 集成测试不得用 SQLite 替代；云模型测试默认使用固定适配器。
- 每个任务遵循红—绿—重构，完成后独立提交。
- 需要 Docker Desktop、联网下载、模型密钥或费用确认时必须暂停并明确指导用户。

---

## 正式阶段计划

1. [阶段 1：工程基础](2026-08-09-backend-phase-1-foundation.md)
2. [阶段 2：物流核心](2026-08-09-backend-phase-2-logistics-core.md)
3. [阶段 3：商业与履约可靠性](2026-08-09-backend-phase-3-commerce-reliability.md)
4. [阶段 4：知识库与 RAG](2026-08-09-backend-phase-4-knowledge-rag.md)
5. [阶段 5：AI Agent](2026-08-09-backend-phase-5-agent.md)
6. [阶段 6：后端收口与 API 冻结](2026-08-09-backend-phase-6-api-freeze.md)

旧计划 `2026-08-09-logistics-core.md` 保留为历史设计依据，不再作为执行入口；其中前端任务不进入本后端计划。

## 阶段顺序与验收门槛

- [ ] 阶段 1：API、PostgreSQL、Redis、Worker、迁移和质量工具可运行。
- [ ] 阶段 2：五角色通过 HTTP 完成四种物流旅程。
- [ ] 阶段 3：正常、异常、支付、SLA、通知和恢复闭环通过。
- [ ] 阶段 4：管理员通过 HTTP 上传 PDF，发布后可检索并引用页码。
- [ ] 阶段 5：对话下单、RAG、工具、授权、记忆和安全评测通过。
- [ ] 阶段 6：全量验证通过，OpenAPI v1 冻结并可生成前端类型。

禁止跳过阶段门槛。某阶段未通过时，只修复该阶段及其已交付依赖，不提前开发前端。

## 跨阶段契约

以下签名是阶段间契约；实施计划中的内部重构不得改变其语义：

```python
class Clock:
    def now(self) -> datetime: ...

class ShipmentApplicationService:
    async def create(
        self,
        command: CreateShipmentCommand,
        actor: CurrentUser,
        idempotency_key: str,
    ) -> ShipmentView: ...

class KnowledgeRetriever:
    async def search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[Evidence]: ...

class ModelAdapter:
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
```

`Agent` 工具只能调用应用服务或 `KnowledgeRetriever`，不得获得 SQLAlchemy Session。`CreateShipmentCommand` 同时服务表单与 AI 草稿确认路径；AI 路径额外消费 `AgentActionGrant`。

## 设计覆盖矩阵

| 设计范围 | 执行计划 |
|---|---|
| 平台、错误、时间、数据库、幂等、审计、Outbox | 阶段 1 |
| 身份、网点、运单、任务、干线、轨迹、签收 | 阶段 2 |
| 计价、支付、SLA/ETA、通知、异常、退回、恢复 | 阶段 3 |
| 文件、解析、发布、索引、检索、引用 | 阶段 4 |
| 对话、双入口下单、工具、授权、记忆、隐私、评测 | 阶段 5 |
| 迁移、演示、安全、性能、OpenAPI 和前端契约 | 阶段 6 |

PRD 中的每项后端验收标准至少映射到上表一个阶段；涉及多个模块的旅程在阶段 6 再执行一次全量回归。
