# 驿途后端阶段五：AI Agent 实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 交付可恢复、可追踪和受控的 LangGraph Agent，支持对话下单、业务查询、RAG 引用、一次性写授权、记忆与安全评测。

**架构：** LangGraph 只管理会话编排；工具调用既有应用服务；数据库保存会话、授权和审计；云模型通过可替换的 OpenAI 兼容适配器接入，CI 使用固定模型。

**技术栈：** LangGraph、OpenAI 兼容 API、SSE、PostgreSQL/pgvector、Redis、pytest 固定模型适配器。

> **进度（2026-08-12）：** 任务一、二已完成。当前使用固定模型适配器完成离线开发和容器内 HTTP 验收；生产聊天模型的 OpenAI 兼容接口在任务七在线冒烟前再配置，不影响继续实现 Agent 工具。

## 全局约束

- 开始在线验证前，明确指导用户选择供应商、创建 API Key、写入 `.env` 并确认费用；不得要求在聊天粘贴密钥。
- 每个图节点、非直观路由和安全边界提供中文 docstring/注释。
- 权限、金额、状态和 SLA 仍由确定性服务裁决；Agent 工具不访问 ORM。

---

### 任务 1：模型适配器、会话持久化与 SSE

**文件：** 新建 `backend/src/yitu/agent/{models,schemas,model_adapter,service,router,sse}.py`；迁移 `0019`；测试 `backend/tests/agent/test_conversations.py`。

**接口：** 产出 `ModelAdapter.complete/stream`、`FixedModelAdapter`、会话/消息路由和 SSE 事件模式。

- [x] 测试用户隔离、重启后恢复、SSE 事件 ID/重连、超时和无密钥降级。
- [x] 实现持久化消息/工具信封、注入式适配器和有界 SSE；默认不得记录完整密钥或提示词。
- [x] 使用固定适配器完成迁移 `0028` 和容器内 HTTP 验收，无需联网即可运行。
- [x] 提交：`功能：新增持久化 Agent 会话`。

### 任务 2：LangGraph 状态与安全路由

**文件：** 新建 `backend/src/yitu/agent/{graph,state,nodes,prompts}.py`；测试 `backend/tests/agent/test_graph_routing.py`。

**接口：** 产出 `AgentState`、`build_agent_graph()`，以及上下文、意图/风险、RAG、查询工具、草稿、确认和响应命名节点。

- [x] 测试公开规则、本人运单、其他客户、草稿更新、敏感动作和提示词注入的路由选择。
- [x] 使用中文 docstring 实现类型化状态和节点；在确定性路由守卫中限制最大轮数、超时和工具预算。
- [x] 用纯内存图测试和固定模型 HTTP 旅程验证普通回复、RAG 动作、本人查询、草稿、确认和拒绝路由。
- [x] 真实 RAG 和只读工具调用保留给任务三，当前节点只返回结构化下一步，绝不伪造业务结果。
- [x] 提交：`功能：定义受控 LangGraph 工作流`。

### 任务 3：只读工具与 RAG 工具

**文件：** 新建 `backend/src/yitu/agent/tools/{base,shipments,pricing,knowledge}.py`；测试 `backend/tests/agent/test_read_tools.py`。

**接口：** 产出严格的 Pydantic 工具，用于查询本人资料/地址、运单/轨迹/费用/ETA 和检索知识库。

- [ ] 测试从 JWT 获取身份、拒绝跨用户访问、精确 DTO、保留引用和无证据响应。
- [ ] 运行只读工具测试；预期因缺少工具而失败。
- [ ] 实现调用应用服务/检索器的适配器，只返回模型所需的最少安全字段。
- [ ] 运行测试；预期全部通过。
- [ ] 提交：`功能：新增范围受控的 Agent 只读工具`。

### 任务 4：运单草稿与双入口共享创建

**文件：** 新建 `backend/src/yitu/agent/drafts.py`；修改运单应用服务；测试 `backend/tests/agent/test_conversation_ordering.py`、`backend/tests/shipments/test_form_ordering.py`。

**接口：** 产出 `DraftService.update/validate/missing_fields`、`CreateShipmentCommand`；表单和 Agent 均调用 `ShipmentApplicationService.create(command)`。

- [ ] 测试多轮补全、用户修正、不支持的地址、禁限寄物品、报价失效、草稿导出到表单和共享创建行为。
- [ ] 运行下单测试；预期因缺少草稿/共享命令而失败。
- [ ] 实现持久化草稿快照和确定性校验/报价调用；AI 只提出结构化字段变更。
- [ ] 同时运行表单与 Agent 下单测试；预期全部通过。
- [ ] 提交：`功能：统一表单与对话下单`。

### 任务 5：AgentActionGrant 与敏感写工具

**文件：** 新建 `backend/src/yitu/agent/{grants,write_tools}.py`；迁移 `0020`；测试 `backend/tests/agent/test_action_grants.py`。

**接口：** 产出 `issue_grant()`、`consume_grant()`，以及经确认的创建运单、异常处理和再次派送工具。

- [ ] 测试授权缺失、过期、已消费、用户错误、动作错误、草稿变化、报价变化和并发消费；每次拒绝都必须审计。
- [ ] 运行授权测试；预期因缺少服务而失败。
- [ ] 实现规范快照哈希、五分钟有效期、nonce 唯一性，并在同一业务事务中原子条件消费。
- [ ] 运行迁移和授权测试；预期全部通过。
- [ ] 提交：`功能：授权 Agent 敏感动作`。

### 任务 6：分层记忆、隐私与删除

**文件：** 新建 `backend/src/yitu/agent/{memory,privacy,context}.py`；迁移 `0021`；测试 `backend/tests/agent/test_memory.py`、`test_privacy.py`。

**接口：** 产出经确认的记忆增删改查、语义检索、上下文组装器，以及 AI 停用/删除端点。

- [ ] 测试显式确认、跨用户隔离、过期、禁止记忆密钥、占位符、最小发送白名单、会话删除和匿名化审计保留。
- [ ] 运行记忆/隐私测试；预期因缺少组件而失败。
- [ ] 实现消息、工作、持久和语义记忆层，并在模型调用前执行确定性脱敏/上下文流水线。
- [ ] 运行迁移和测试；预期全部通过。
- [ ] 提交：`功能：新增私密分层 Agent 记忆`。

### 任务 7：追踪、评测集、在线冒烟与阶段验收

**文件：** 新建 `backend/src/yitu/agent/tracing.py`；新建 `backend/evals/cases/*.yaml`；测试 `backend/tests/agent/test_evals.py`；添加 README Agent 指南。

**接口：** 产出贯穿 API、检索、工具和审计的追踪 ID，以及确定性评测报告。

- [ ] 添加 30–50 个用例，覆盖抽取、工具、引用、注入、拒答、授权、记忆和降级；写入 PRD 阈值。
- [ ] 运行固定适配器 CI 评测；要求安全门槛 100%、工具/抽取 ≥95%、完成/引用 ≥90%，且禁止结果为零。
- [ ] 请求用户批准供应商、密钥和费用后，再运行有界在线冒烟测试，且不得打印密钥。
- [ ] 运行 `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`；预期全部通过。
- [ ] 提交：`测试：验证安全 AI Agent 行为`。
