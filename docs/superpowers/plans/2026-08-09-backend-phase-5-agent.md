# Yitu Backend Phase 5 AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可恢复、可追踪和受控的 LangGraph Agent，支持对话下单、业务查询、RAG 引用、一次性写授权、记忆与安全评测。

**Architecture:** LangGraph 只管理会话编排；工具调用既有应用服务；数据库保存会话、授权和审计；云模型通过可替换 OpenAI-compatible 适配器接入，CI 使用固定模型。

**Tech Stack:** LangGraph、OpenAI-compatible API、SSE、PostgreSQL/pgvector、Redis、pytest 固定模型适配器。

## Global Constraints

- 开始在线验证前，明确指导用户选择供应商、创建 API Key、写入 `.env` 并确认费用；不得要求在聊天粘贴密钥。
- 每个图节点、非直观路由和安全边界提供中文 docstring/注释。
- 权限、金额、状态和 SLA 仍由确定性服务裁决；Agent 工具不访问 ORM。

---

### Task 1: Model Adapter, Conversation Persistence, and SSE

**Files:** Create `backend/src/yitu/agent/{models,schemas,model_adapter,service,router,sse}.py`; migration `0019`; tests `backend/tests/agent/test_conversations.py`.

**Interfaces:** Produces `ModelAdapter.complete/stream`, `FixedModelAdapter`, conversation/message routes and SSE event schema.

- [ ] Test user isolation, resume after restart, SSE event IDs/reconnect, timeout and no-key degradation.
- [ ] Run agent conversation tests; expect missing module.
- [ ] Implement persisted messages/tool envelopes, injected adapter and bounded SSE; never log full secrets/prompts by default.
- [ ] Run migration and tests with fixed adapter; expect all pass without network.
- [ ] Commit `feat: add persistent agent conversations`.

### Task 2: LangGraph State and Safe Routing

**Files:** Create `backend/src/yitu/agent/{graph,state,nodes,prompts}.py`; tests `backend/tests/agent/test_graph_routing.py`.

**Interfaces:** Produces `AgentState`, `build_agent_graph()`, named nodes for context, intent/risk, RAG, query tool, draft, confirmation and response.

- [ ] Test route selection for public rule, own shipment, other customer, draft update, sensitive action and prompt injection.
- [ ] Run graph tests; expect missing graph.
- [ ] Implement typed state and nodes with Chinese docstrings; enforce maximum rounds, timeout and tool budget in deterministic routing guards.
- [ ] Run graph tests; expect all pass.
- [ ] Commit `feat: define controlled LangGraph workflow`.

### Task 3: Read Tools and RAG Tool

**Files:** Create `backend/src/yitu/agent/tools/{base,shipments,pricing,knowledge}.py`; tests `backend/tests/agent/test_read_tools.py`.

**Interfaces:** Produces strict Pydantic tools for own profile/address, shipment/tracking/fee/ETA query and knowledge search.

- [ ] Test JWT-derived identity, cross-user refusal, exact DTOs, citation preservation and no-evidence response.
- [ ] Run read-tool tests; expect missing tools.
- [ ] Implement adapters that call application services/retriever and return only minimum model-safe fields.
- [ ] Run tests; expect all pass.
- [ ] Commit `feat: add scoped agent read tools`.

### Task 4: ShipmentDraft and Dual-Entry Shared Creation

**Files:** Create `backend/src/yitu/agent/drafts.py`; modify shipment application service; tests `backend/tests/agent/test_conversation_ordering.py`, `backend/tests/shipments/test_form_ordering.py`.

**Interfaces:** Produces `DraftService.update/validate/missing_fields`, `CreateShipmentCommand`; both form and Agent call `ShipmentApplicationService.create(command)`.

- [ ] Test multi-turn completion, user correction, unsupported address, restricted item, quote invalidation, draft-to-form export and shared creation behavior.
- [ ] Run ordering tests; expect missing draft/shared command.
- [ ] Implement persisted draft snapshots and deterministic validation/quote calls; AI only proposes structured field changes.
- [ ] Run both form and Agent ordering tests; expect all pass.
- [ ] Commit `feat: unify form and conversational ordering`.

### Task 5: AgentActionGrant and Sensitive Write Tools

**Files:** Create `backend/src/yitu/agent/{grants,write_tools}.py`; migration `0020`; tests `backend/tests/agent/test_action_grants.py`.

**Interfaces:** Produces `issue_grant()`, `consume_grant()`, confirmed create-shipment/exception/redelivery tools.

- [ ] Test missing, expired, consumed, wrong-user, wrong-action, changed-draft, changed-quote and concurrent consumption; every rejection must audit.
- [ ] Run grant tests; expect missing service.
- [ ] Implement canonical snapshot hashes, five-minute expiry, nonce uniqueness and atomic conditional consumption in the same business transaction.
- [ ] Run migration and grant tests; expect all pass.
- [ ] Commit `feat: authorize sensitive agent actions`.

### Task 6: Layered Memory, Privacy, and Deletion

**Files:** Create `backend/src/yitu/agent/{memory,privacy,context}.py`; migration `0021`; tests `backend/tests/agent/test_memory.py`, `test_privacy.py`.

**Interfaces:** Produces confirmed memory CRUD, semantic retrieval, context assembler, AI disable/delete endpoints.

- [ ] Test explicit confirmation, cross-user isolation, expiry, prohibited secret memory, placeholders, minimum-send whitelist, conversation deletion and anonymized audit retention.
- [ ] Run memory/privacy tests; expect missing components.
- [ ] Implement message/work/durable/semantic layers and a deterministic redaction/context pipeline before model calls.
- [ ] Run migration and tests; expect all pass.
- [ ] Commit `feat: add private layered agent memory`.

### Task 7: Tracing, Evaluation Suite, Online Smoke, and Phase Gate

**Files:** Create `backend/src/yitu/agent/tracing.py`; create `backend/evals/cases/*.yaml`; tests `backend/tests/agent/test_evals.py`; add README Agent guide.

**Interfaces:** Produces trace IDs across API/retrieval/tool/audit and deterministic evaluation report.

- [ ] Add 30–50 cases covering extraction, tools, citations, injection, refusal, grants, memory and degradation; encode PRD thresholds.
- [ ] Run fixed-adapter CI eval; require 100% security gates, ≥95% tool/extraction, ≥90% completion/citation and zero forbidden outcomes.
- [ ] Ask user for provider/key/fee approval, then run a bounded online smoke test without printing secrets.
- [ ] Run `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`; expect all pass.
- [ ] Commit `test: verify safe AI agent behavior`.
