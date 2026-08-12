# 驿途后端阶段五：AI Agent 实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 交付可恢复、可追踪和受控的 LangGraph Agent，支持对话下单、业务查询、RAG 引用、一次性写授权、记忆与安全评测。

**架构：** LangGraph 只管理会话编排；工具调用既有应用服务；数据库保存会话、授权和审计；云模型通过可替换的 OpenAI 兼容适配器接入，CI 使用固定模型。

**技术栈：** LangGraph、OpenAI 兼容 API、SSE、PostgreSQL/pgvector、Redis、pytest 固定模型适配器。

> **进度（2026-08-12）：** 任务一至三已完成。当前使用固定模型适配器完成离线开发和容器内 HTTP 验收；生产聊天模型的 OpenAI 兼容接口在任务七在线冒烟前再配置，不影响继续实现 Agent 草稿和授权。

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

- [x] 测试从 JWT 获取身份、拒绝跨用户访问、精确 DTO、保留引用和无证据响应。
- [x] 实现调用应用服务/检索器的适配器，只返回模型所需的最少安全字段。
- [x] 用固定适配器和真实容器知识库验证运单查询、RAG 引用和空结果边界。
- [x] 提交：`功能：新增范围受控的 Agent 只读工具`。

### 任务 4：运单草稿与双入口共享创建

**文件：** 新建 `backend/src/yitu/agent/drafts.py`；修改运单应用服务；测试 `backend/tests/agent/test_conversation_ordering.py`、`backend/tests/shipments/test_form_ordering.py`。

**接口：** 产出 `DraftService.update/validate/missing_fields`、`CreateShipmentCommand`；表单和 Agent 均调用 `ShipmentApplicationService.create(command)`。

- [x] 测试多轮补全、用户修正、不支持的地址、禁限寄物品、报价失效、草稿导出到表单和共享创建行为。
- [x] 运行下单测试；表单入口已复用共享命令和应用服务，正式写入留给任务五授权流程。
- [x] 实现持久化草稿快照和确定性校验/报价调用；AI 只提出结构化字段变更。
- [x] 同时完成表单与 Agent 的共享命令契约，并通过 Compose HTTP 验收草稿、报价和报价失效流程。
- [x] 提交：`功能：统一表单与对话下单`。

### 任务 5：AgentActionGrant 与敏感写工具

**文件：** 新建 `backend/src/yitu/agent/{grants,write_tools}.py`；迁移 `0020`；测试 `backend/tests/agent/test_action_grants.py`。

**接口：** 产出 `issue_grant()`、`consume_grant()`，以及经确认的创建运单、异常处理和再次派送工具。

- [x] 实现授权缺失、过期、已消费、用户错误、草稿变化和报价变化的确定性拒绝；每次拒绝写入审计。
- [x] 通过容器 HTTP 验证授权签发、正式运单创建、重复消费和草稿变化拒绝。
- [x] 实现规范快照哈希、五分钟有效期、nonce 唯一性，并在同一业务事务中行锁消费。
- [x] 迁移头为 `0030`，Ruff/mypy 通过；正式创建复用 `ShipmentApplicationService.create`。
- [x] 提交：`功能：授权 Agent 敏感动作`。

### 任务 6：分层记忆、隐私与删除

**文件：** 新建 `backend/src/yitu/agent/{memory,privacy,context}.py`；迁移 `0021`；测试 `backend/tests/agent/test_memory.py`、`test_privacy.py`。

**接口：** 产出经确认的记忆增删改查、语义检索、上下文组装器，以及 AI 停用/删除端点。

- [x] 实现显式确认、用户隔离、过期过滤、禁止记忆密钥/令牌/联系方式、最小模型上下文和会话删除。
- [x] 通过容器 HTTP 验收敏感记忆拒绝、正常记忆创建/查询/删除及会话删除后的 404。
- [x] 实现消息记忆、单次工作上下文、持久记忆和模型调用前确定性脱敏流水线。
- [x] 迁移头为 `0031`，Ruff/mypy 通过。
- [x] 提交：`功能：新增私密分层 Agent 记忆`。

### 任务 7：追踪、评测集、在线冒烟与阶段验收

**文件：** 新建 `backend/src/yitu/agent/tracing.py`；新建 `backend/evals/cases/*.yaml`；测试 `backend/tests/agent/test_evals.py`；添加 README Agent 指南。

**接口：** 产出贯穿 API、检索、工具和审计的追踪 ID，以及确定性评测报告。

- [x] 添加固定评测用例，覆盖知识检索、本人查询、草稿、敏感确认、提示词注入、越权拒绝、隐私脱敏和普通对话。
- [x] 运行固定适配器评测：安全路由和隐私用例 `9/9` 通过；DeepSeek 在线冒烟已通过有界请求。
- [x] 新增有界 `AgentTrace` 和消息信封 `trace_id`，可关联图路由、工具和模型事件。
- [x] 补充 `docs/agent.md` 使用指南和验收边界；Ruff/mypy/固定评测通过。
- [x] 提交：`测试：验证安全 AI Agent 行为`；在线验收收口记录见 `docs/agent.md`。
