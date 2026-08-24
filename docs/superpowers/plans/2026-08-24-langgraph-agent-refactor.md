# LangGraph Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将驿途统一 AI 助手重构为由 LangGraph 1.2.11 真正拥有控制流、两个受限 ReAct 循环、寄件子图、PostgreSQL checkpoint 和 HITL 恢复的 Agent，同时保持现有 REST/SSE 契约与确定性业务安全边界。

**Architecture:** 主图使用 `AssistantState` 编排上下文、安全守卫、通用工具循环、寄件 handoff、显式失败和最终持久化；寄件子图使用独立 `ShipmentState` 编排草稿工具循环、确定性校验报价、`interrupt/resume` 和原子建单。节点通过少量深 Port 调用现有业务模块，`AgentRuntime` 统一 invoke、stream、resume 和 SSE 映射，`AgentConversationService` 最终只保留会话 CRUD 与兼容门面。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、SQLAlchemy asyncio、LangGraph 1.2.11、langgraph-checkpoint-postgres 3.1.2、PostgreSQL/pgvector、pytest 8、pytest-asyncio、OpenAI-compatible model adapter、SSE。

## Global Constraints

- 严格执行 TDD：每个行为先写测试，确认因缺少功能而失败，再写最小实现。
- 不使用共享开发库清理作为测试隔离手段；纯节点和图测试必须使用内存 Port 与 `MemorySaver`。
- PostgreSQL 集成测试只允许连接显式的 `YITU_TEST_DATABASE_URL`，且数据库名必须以 `_test` 结尾；不满足时跳过而不是清理开发库。
- 现有前端 REST 路径、`AgentTurnView` 和 SSE `user_message/delta/done/error` 契约不变。
- 节点函数统一以 `_node` 结尾，条件边以 `_route` 结尾，图工厂以 `build_*_graph` 命名。
- 新增注释和 docstring 使用简体中文，只解释安全不变量、恢复原因和非直观控制流。
- 主图与子图使用独立 State，通过 `ShipmentHandoff` / `ShipmentWorkflowResult` 交换最小信息。
- checkpoint 只保存可序列化工作流数据；ORM、Session、模型实例、完整敏感资料和可执行授权对象不得进入 State。
- 模型只能自主调用白名单只读工具和草稿工具；报价、授权、建单和权限裁决保持确定性。
- `knowledge` 模块继续独立；Agent 只通过 `KnowledgePort` 调用在线检索。
- 子图不配置独立 saver，不覆盖父图 config；父图 `thread_id` 与 checkpoint namespace 自动传播。
- 保留显式 `handle_failure_node`；未知异常由 Runtime 兜底。
- 不长期保留 legacy/new 双执行路径；新 Runtime 契约测试通过后立即删除旧图外编排。
- 保护当前未提交的 `service.py`、`draft_loop.py` 用户注释意图；删除旧文件时只迁移仍有解释价值的注释，不覆盖其他用户文件。

---

## File Map

### New production modules

```text
backend/src/yitu/agent/
├── runtime/
│   ├── __init__.py
│   ├── context.py                 # Runtime context 与生产依赖装配
│   ├── event_mapper.py            # 内部事件到四类公开事件
│   └── runtime.py                 # invoke/stream/resume/thread 生命周期
├── workflows/
│   ├── __init__.py
│   ├── assistant_graph.py         # 7 节点主图
│   └── shipment_graph.py          # 8 节点寄件子图
├── workflow_state/
│   ├── __init__.py
│   ├── assistant.py               # AssistantState
│   ├── shipment.py                # ShipmentState
│   └── contracts.py               # Handoff/Result/Error/Event DTO
├── workflow_nodes/
│   ├── __init__.py
│   ├── context_nodes.py
│   ├── assistant_nodes.py
│   ├── shipment_nodes.py
│   └── finalize_nodes.py
├── ports/
│   ├── __init__.py
│   ├── conversation.py
│   ├── model.py
│   ├── knowledge.py
│   ├── assistant_reads.py
│   ├── shipment_workflow.py
│   └── tracing.py
└── adapters/
    ├── __init__.py
    ├── conversation.py
    ├── model.py
    ├── knowledge.py
    ├── assistant_reads.py
    ├── shipment_workflow.py
    └── tracing.py
```

### New tests

```text
backend/tests/
├── conftest.py
└── agent/
    ├── fakes.py
    ├── test_workflow_contracts.py
    ├── test_assistant_nodes.py
    ├── test_assistant_graph.py
    ├── test_shipment_nodes.py
    ├── test_shipment_graph.py
    ├── test_runtime.py
    ├── test_sse_contract.py
    ├── test_postgres_resume.py
    └── test_confirmation_concurrency.py
```

### Modified modules

- `backend/src/yitu/agent/model_adapter.py`: 保留供应商适配，增加工作流 Port 需要的结构化工具调用契约。
- `backend/src/yitu/agent/checkpoint_store.py`: 支持已编译根图生命周期和 thread 删除。
- `backend/src/yitu/agent/service.py`: 删除图外编排，保留会话 CRUD、草稿地址兼容方法和 Runtime 门面。
- `backend/src/yitu/agent/router.py`: 注入 Runtime，保持公开接口不变。
- `backend/src/yitu/agent/sse.py`: 复用稳定编码器，移除重复事件映射职责。
- `backend/src/yitu/main.py`: 在 lifespan 中初始化/释放已编译 Agent Runtime。
- `backend/evals/run.py`: 改为运行完整图的确定性评测。
- `backend/evals/cases/*.yaml`: 更新为工具选择、工作流和授权行为用例。
- `docs/agent.md`、`docs/agent-rag-architecture.md`、`docs/interview-script.md`、`docs/demo-script.md`: 删除旧架构说法。

### Deleted legacy modules after cutover

- `backend/src/yitu/agent/graph.py`
- `backend/src/yitu/agent/nodes.py`
- `backend/src/yitu/agent/state.py`
- `backend/src/yitu/agent/draft_loop.py`
- `backend/src/yitu/agent/understanding.py`

---

### Task 1: Rebuild Isolated Test Foundations and Freeze Public Contracts

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/agent/fakes.py`
- Create: `backend/tests/agent/test_workflow_contracts.py`
- Create: `backend/tests/agent/test_sse_contract.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: existing `MessageView`, `AgentTurnView`, `encode_agent_event`, `ModelAdapter` DTOs.
- Produces: reusable `FakeModelPort`, `FakeKnowledgePort`, `FakeAssistantReadPort`, `FakeShipmentWorkflowPort`, `FakeConversationPort`, `FakeTracePort`; isolated pytest configuration used by all later tasks.

- [ ] **Step 1: Write a failing safety test for test database isolation**

```python
def test_database_tests_reject_non_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "YITU_TEST_DATABASE_URL",
        "postgresql+asyncpg://user:pass@localhost/yitu",
    )
    with pytest.raises(RuntimeError, match="_test"):
        require_test_database_url()
```

The production change this catches is accidentally running destructive integration setup against the development database.

- [ ] **Step 2: Run the safety test and verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_workflow_contracts.py::test_database_tests_reject_non_test_database -q
```

Expected: FAIL because `require_test_database_url` does not exist.

- [ ] **Step 3: Implement the isolated test helper and pytest paths**

`backend/tests/conftest.py` must expose `require_test_database_url()` and must not register an autouse cleanup fixture:

```python
def require_test_database_url() -> str:
    url = os.environ.get("YITU_TEST_DATABASE_URL", "")
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not url or not database.endswith("_test"):
        raise RuntimeError("YITU_TEST_DATABASE_URL 必须指向以 _test 结尾的独立数据库")
    return url
```

Set `testpaths = ["tests"]` in `pyproject.toml`. Do not restore the historical shared-database cleanup fixture.

- [ ] **Step 4: Add behavior-first fake Ports**

`fakes.py` fakes must return complete DTOs and record observable domain actions, not expose mock assertions. Example:

```python
class FakeKnowledgePort:
    def __init__(self, evidence: KnowledgeEvidence) -> None:
        self.evidence = evidence
        self.queries: list[KnowledgeSearchInput] = []

    async def search(self, request: KnowledgeSearchInput, *, actor_id: UUID) -> KnowledgeEvidence:
        self.queries.append(request)
        return self.evidence
```

- [ ] **Step 5: Freeze current SSE and non-streaming contracts**

Add tests that assert literal public behavior:

```python
def test_agent_sse_contract_keeps_four_public_event_shapes() -> None:
    assert encode_agent_event("delta", {"content": "你"}) == (
        'event: delta\ndata: {"content": "你"}\n\n'
    )

def test_agent_turn_view_keeps_user_and_assistant_messages() -> None:
    turn = AgentTurnView(user_message=user_view, assistant_message=assistant_view)
    assert set(turn.model_dump()) == {"user_message", "assistant_message"}
```

- [ ] **Step 6: Run Task 1 tests and verify GREEN**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_workflow_contracts.py tests/agent/test_sse_contract.py -q
```

Expected: all tests pass without connecting to PostgreSQL.

- [ ] **Step 7: Commit Task 1**

```powershell
git add backend/pyproject.toml backend/tests
git commit -m "测试(agent)：重建隔离测试与接口契约"
```

---

### Task 2: Define Workflow States, DTOs, Ports, and Production Adapters

**Files:**
- Create: `backend/src/yitu/agent/workflow_state/{__init__,assistant,shipment,contracts}.py`
- Create: `backend/src/yitu/agent/ports/{__init__,conversation,model,knowledge,assistant_reads,shipment_workflow,tracing}.py`
- Create: `backend/src/yitu/agent/adapters/{__init__,conversation,model,knowledge,assistant_reads,shipment_workflow,tracing}.py`
- Test: `backend/tests/agent/test_workflow_contracts.py`

**Interfaces:**
- Consumes: existing `ModelAdapter`, `KnowledgeSearchTool`, read tools, `DraftService`, `GrantService`, `AgentWriteService`, `AgentTrace`.
- Produces: `AssistantState`, `ShipmentState`, `ShipmentHandoff`, `ShipmentWorkflowResult`, `WorkflowError`, `AgentRuntimeContext`, and six deep Ports used by every node.

- [ ] **Step 1: Write failing DTO serialization tests**

```python
def test_shipment_handoff_rejects_identity_and_quote_fields() -> None:
    with pytest.raises(ValidationError):
        ShipmentHandoff.model_validate({
            "user_message": "寄衣服",
            "extracted_fields": {},
            "user_id": str(uuid4()),
        })

def test_workflow_error_is_checkpoint_serializable() -> None:
    error = WorkflowError(
        code="QUOTE_EXPIRED",
        message="报价已失效",
        source_node="create_quote_node",
    )
    assert json.loads(error.model_dump_json())["retryable"] is False
```

Expected RED: modules do not exist.

- [ ] **Step 2: Implement minimal DTOs and State schemas**

Use `extra="forbid"` on cross-graph DTOs. Store Pydantic models as `model_dump(mode="json")` in State. Message reducers operate on `list[dict[str, object]]`, never custom dataclass instances.

- [ ] **Step 3: Write failing Port contract tests**

Test observable results from real production adapters using a fake Session only where the existing tool already isolates I/O. At minimum verify:

- `AssistantReadPort` never accepts `user_id` from tool arguments;
- `KnowledgePort` returns `found=False` with no citations instead of invoking answer generation;
- `ShipmentWorkflowPort.create_confirmed()` delegates to the existing grant/write path as one method.

- [ ] **Step 4: Implement Port protocols and adapters**

Key interfaces:

```python
class ModelPort(Protocol):
    def stream_with_tools(
        self,
        messages: Sequence[dict[str, object]],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]: ...

class KnowledgePort(Protocol):
    async def search(
        self, request: KnowledgeSearchInput, *, actor_id: UUID
    ) -> KnowledgeEvidence: ...

class AssistantReadPort(Protocol):
    async def execute(
        self, call: AssistantToolCall, *, actor_id: UUID
    ) -> AssistantToolObservation: ...

class ShipmentWorkflowPort(Protocol):
    async def load_progress(self, conversation_id: UUID, actor_id: UUID) -> DraftProgress: ...
    async def execute_draft_tool(self, conversation_id: UUID, actor_id: UUID, call: DraftToolCall) -> DraftProgress: ...
    async def validate_and_quote(self, conversation_id: UUID, actor_id: UUID) -> QuoteProgress: ...
    async def prepare_confirmation(self, conversation_id: UUID, actor_id: UUID) -> ConfirmationSnapshot: ...
    async def create_confirmed(self, conversation_id: UUID, actor_id: UUID, request_id: str) -> ShipmentReceipt: ...
```

The production shipment adapter may reconstruct `CurrentUser` from trusted Runtime context; model arguments can never supply it.

- [ ] **Step 5: Run Task 2 tests and type checking**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_workflow_contracts.py -q
uv run mypy src/yitu/agent/workflow_state src/yitu/agent/ports src/yitu/agent/adapters
uv run ruff check src/yitu/agent/workflow_state src/yitu/agent/ports src/yitu/agent/adapters tests/agent
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/src/yitu/agent/workflow_state backend/src/yitu/agent/ports backend/src/yitu/agent/adapters backend/tests/agent
git commit -m "重构(agent)：建立工作流状态与深端口"
```

---

### Task 3: Implement the Seven-Node Assistant Graph and ReAct Loop

**Files:**
- Create: `backend/src/yitu/agent/workflow_nodes/context_nodes.py`
- Create: `backend/src/yitu/agent/workflow_nodes/assistant_nodes.py`
- Create: `backend/src/yitu/agent/workflow_nodes/finalize_nodes.py`
- Create: `backend/src/yitu/agent/workflows/assistant_graph.py`
- Create: `backend/tests/agent/test_assistant_nodes.py`
- Create: `backend/tests/agent/test_assistant_graph.py`

**Interfaces:**
- Consumes: `AssistantState`, `AgentRuntimeContext`, Model/Knowledge/AssistantRead/Conversation/Trace Ports.
- Produces: `build_assistant_graph(shipment_graph)`, seven named nodes, `assistant_action_route`, `failure_route`.

- [ ] **Step 1: Write failing tests for direct answer and one-tool loop**

```python
async def test_assistant_graph_observes_tool_result_before_answer() -> None:
    model = ScriptedModelPort([
        tool_call("search_knowledge", {"query": "充电宝寄递规则"}),
        final_text("根据已发布规则，充电宝不能按普通物品寄递。"),
    ])
    result = await graph.ainvoke(base_input, context=context_with(model))
    assert result["response"] == "根据已发布规则，充电宝不能按普通物品寄递。"
    assert [item["role"] for item in result["messages"]][-2:] == ["tool", "assistant"]
```

Expected RED: graph does not exist.

- [ ] **Step 2: Implement context and security nodes**

`load_context_node` loads and sanitizes only the latest bounded history. `security_gate_node` reuses pure safety rules, returns `WorkflowError` on blocked input, and never calls the model.

- [ ] **Step 3: Implement assistant Agent and tools nodes**

`assistant_agent_node` uses `ModelPort.stream_with_tools`; every non-empty token writes an internal `TokenGenerated` event through `StreamWriter`. Final tool calls are appended as an assistant message.

`assistant_tools_node` validates each call against the five-tool registry. Knowledge calls use `KnowledgePort`; other reads use `AssistantReadPort`. Unknown or write-like tool names produce a safe `WorkflowError`, never arbitrary dispatch.

- [ ] **Step 4: Implement routes and graph assembly**

```python
def assistant_action_route(state: AssistantState) -> Literal[
    "assistant_tools_node", "shipment_workflow_node", "finalize_turn_node", "handle_failure_node"
]:
    if state.get("error"):
        return "handle_failure_node"
    if state.get("shipment_handoff"):
        return "shipment_workflow_node"
    if last_message_has_tool_calls(state):
        return "assistant_tools_node"
    return "finalize_turn_node"
```

Increment `turn_count` at each Agent invocation and `tool_call_count` by the number of executed calls. Route to failure when limits are reached.

- [ ] **Step 5: Add tests for multi-tool, budget, unknown tool, injection, and handoff**

Tests must assert final graph behavior, not internal mock calls:

- two tool observations precede final answer;
- fifth tool request is refused at `max_tool_calls=4`;
- unknown tool cannot execute;
- injection request never reaches model fake;
- structured shipment handoff enters the supplied child graph.

- [ ] **Step 6: Run Task 3 tests**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_assistant_nodes.py tests/agent/test_assistant_graph.py -q
uv run mypy src/yitu/agent/workflow_nodes src/yitu/agent/workflows/assistant_graph.py
uv run ruff check src/yitu/agent/workflow_nodes src/yitu/agent/workflows/assistant_graph.py tests/agent
```

- [ ] **Step 7: Commit Task 3**

```powershell
git add backend/src/yitu/agent/workflow_nodes backend/src/yitu/agent/workflows backend/tests/agent
git commit -m "功能(agent)：实现助手 ReAct 主图"
```

---

### Task 4: Implement the Eight-Node Shipment Subgraph and HITL

**Files:**
- Create: `backend/src/yitu/agent/workflow_nodes/shipment_nodes.py`
- Create: `backend/src/yitu/agent/workflows/shipment_graph.py`
- Create: `backend/tests/agent/test_shipment_nodes.py`
- Create: `backend/tests/agent/test_shipment_graph.py`
- Modify: `backend/src/yitu/agent/workflows/assistant_graph.py`

**Interfaces:**
- Consumes: `ShipmentHandoff`, `ShipmentState`, `ShipmentWorkflowPort`, `ModelPort`.
- Produces: `build_shipment_graph()`, eight named nodes, draft ReAct loop, `interrupt` payload, `ShipmentWorkflowResult`.

- [ ] **Step 1: Write failing draft loop tests**

```python
async def test_draft_agent_executes_tool_then_reloads_progress() -> None:
    model = ScriptedModelPort([
        tool_call("update_draft", {"estimated_weight_grams": 3000}),
        final_text("还需要收件地址。"),
    ])
    result = await shipment_graph.ainvoke(input_state, context=context_with(model))
    assert result["workflow_result"]["status"] == "NEEDS_INPUT"
    assert result["workflow_result"]["response"] == "还需要收件地址。"
```

Expected RED: child graph does not exist.

- [ ] **Step 2: Implement draft nodes and routes**

`load_draft_node` always reloads `DraftProgress` from Port. `draft_agent_node` can only see and call `inspect_draft`, `update_draft`, `save_address`. `draft_tools_node` executes through `ShipmentWorkflowPort`, then returns to the Agent.

When the Agent emits no tool call:

- missing fields → return `NEEDS_INPUT`;
- complete draft → route to `validate_draft_node`.

- [ ] **Step 3: Write failing quote and interrupt tests**

```python
async def test_complete_draft_interrupts_with_versioned_confirmation() -> None:
    config = {"configurable": {"thread_id": "shipment-confirm"}}
    first = await shipment_graph.ainvoke(input_state, config=config, context=context)
    interrupt_value = first["__interrupt__"][0].value
    assert interrupt_value["kind"] == "shipment_confirmation"
    assert interrupt_value["draft_revision"] == 3
    assert interrupt_value["quote_version"] == "pricing-v2"
```

Expected RED: no interrupt exists.

- [ ] **Step 4: Implement deterministic transaction nodes and interrupt**

`validate_draft_node` and `create_quote_node` call Port methods; they do not call the model. `await_confirmation_node` first prepares a public summary, then calls:

```python
decision = interrupt(confirmation.model_dump(mode="json"))
return {"confirmation_decision": ConfirmationDecision.model_validate(decision).decision}
```

On confirm, `reload_confirmation_facts_node` compares current DB facts with `draft_revision_seen`, `quote_id_seen`, and `quote_version_seen`. On stale facts, return a `WorkflowError` requiring re-quote.

`create_confirmed_shipment_node` makes exactly one Port call: `create_confirmed(...)`.

- [ ] **Step 5: Prove nested independent State and parent resume**

Compile the child without a saver. Add it through `shipment_workflow_node`, whose implementation calls `shipment_graph.ainvoke(child_input)` without passing a new config. Test:

```python
parent = build_assistant_graph(build_shipment_graph()).compile(checkpointer=MemorySaver())
first = await parent.ainvoke(message_input, config=thread, context=context)
assert first["__interrupt__"]
second = await parent.ainvoke(Command(resume={"decision": "confirm"}), config=thread, context=context)
assert second["shipment_result"]["status"] == "CREATED"
```

- [ ] **Step 6: Add cancel, defer, stale fact, and repeated resume tests**

- cancel returns `CANCELLED` without calling create;
- defer returns `DEFERRED` and permits Runtime to process the original message as a new main-graph input;
- changed revision/version returns `FAILED` and never creates shipment;
- resume after completion cannot create a second shipment.

- [ ] **Step 7: Run Task 4 tests**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_shipment_nodes.py tests/agent/test_shipment_graph.py tests/agent/test_assistant_graph.py -q
uv run mypy src/yitu/agent/workflow_nodes/shipment_nodes.py src/yitu/agent/workflows
uv run ruff check src/yitu/agent/workflow_nodes/shipment_nodes.py src/yitu/agent/workflows tests/agent
```

- [ ] **Step 8: Commit Task 4**

```powershell
git add backend/src/yitu/agent/workflow_nodes/shipment_nodes.py backend/src/yitu/agent/workflows backend/tests/agent
git commit -m "功能(agent)：实现可恢复寄件子图"
```

---

### Task 5: Build AgentRuntime, Event Mapping, and Compiled Graph Lifecycle

**Files:**
- Create: `backend/src/yitu/agent/runtime/{__init__,context,event_mapper,runtime}.py`
- Create: `backend/tests/agent/test_runtime.py`
- Modify: `backend/src/yitu/agent/checkpoint_store.py`
- Modify: `backend/src/yitu/main.py`

**Interfaces:**
- Consumes: compiled assistant graph, shared checkpointer, Runtime context adapters.
- Produces: `AgentRuntime.invoke_message`, `AgentRuntime.stream_message`, deterministic resume/defer behavior, process-level graph lifecycle.

- [ ] **Step 1: Write failing event mapper tests**

```python
def test_internal_token_maps_to_existing_delta_contract() -> None:
    assert mapper.map(TokenGenerated(content="驿")) == (
        "delta", {"content": "驿"}
    )

def test_node_trace_is_not_exposed_to_frontend() -> None:
    assert mapper.map(NodeCompleted(node="assistant_tools_node")) is None
```

- [ ] **Step 2: Implement internal event DTOs and mapper**

Only `UserMessageStored`, `TokenGenerated`, `AssistantMessageStored`, and `WorkflowFailed` map to public events. Trace/tool/node events remain internal.

- [ ] **Step 3: Write failing Runtime tests for invoke/stream reuse**

Assert both interfaces call the same compiled graph behavior and yield the literal event order:

```text
user_message → delta* → done
```

No alternate non-streaming execution branch is allowed.

- [ ] **Step 4: Implement Runtime and deterministic pending-interrupt handling**

Before a new invocation, inspect graph state for interrupts:

- explicit confirm → `Command(resume={"decision": "confirm"})`;
- explicit cancel → `Command(resume={"decision": "cancel"})`;
- other text → resume with `defer`, wait for that run to finish, then invoke the original text as new input.

Confirmation/cancellation detection must use normalized deterministic phrases and must not call the model.

- [ ] **Step 5: Compile the graph once per process lifecycle**

Add lazy, lock-protected runtime initialization beside the existing checkpointer lifecycle. `main.lifespan` disposes runtime/checkpointer resources. Add `delete_thread(conversation_id)` for conversation deletion.

- [ ] **Step 6: Add Runtime error tests**

- known `WorkflowError` reaches explicit failure/finalize path;
- unexpected exception produces one public `error` event with stable code;
- unexpected exception never produces `done`;
- incomplete streamed response is not persisted as success.

- [ ] **Step 7: Run Task 5 tests and static checks**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_runtime.py tests/agent/test_sse_contract.py -q
uv run mypy src/yitu/agent/runtime src/yitu/agent/checkpoint_store.py
uv run ruff check src/yitu/agent/runtime src/yitu/agent/checkpoint_store.py src/yitu/main.py tests/agent
```

- [ ] **Step 8: Commit Task 5**

```powershell
git add backend/src/yitu/agent/runtime backend/src/yitu/agent/checkpoint_store.py backend/src/yitu/main.py backend/tests/agent
git commit -m "功能(agent)：接入工作流运行时与事件映射"
```

---

### Task 6: Cut Over Service and Router, Then Delete Legacy Orchestration

**Files:**
- Modify: `backend/src/yitu/agent/service.py`
- Modify: `backend/src/yitu/agent/router.py`
- Modify: `backend/src/yitu/agent/sse.py`
- Modify: `backend/src/yitu/agent/model_adapter.py`
- Delete: `backend/src/yitu/agent/{graph,nodes,state,draft_loop,understanding}.py`
- Create: `backend/tests/agent/test_service_compatibility.py`

**Interfaces:**
- Consumes: `AgentRuntime`, current FastAPI dependencies and public schemas.
- Produces: unchanged REST/SSE behavior with no legacy route execution path.

- [ ] **Step 1: Write failing compatibility tests against the wished-for thin service**

Test `send_message` and `stream_message` through a fake Runtime and assert returned public behavior. The fake Runtime is the seam; do not mock internal nodes.

```python
async def test_service_stream_forwards_runtime_public_events() -> None:
    service = AgentConversationService(session, runtime=fake_runtime)
    assert [event async for event in service.stream_message(...)] == [
        ("user_message", user_payload),
        ("delta", {"content": "完成"}),
        ("done", assistant_payload),
    ]
```

Expected RED: service does not accept Runtime.

- [ ] **Step 2: Replace `_run_turn` with Runtime delegation**

Keep only:

- create/list/get/delete conversation;
- list messages;
- existing draft-address compatibility endpoint behavior;
- record external grant-consumption receipt if still used by the button path;
- `send_message` / `stream_message` Runtime delegation.

All routing, model, RAG, draft, quote, confirmation and shipment execution moves out.

- [ ] **Step 3: Update FastAPI dependency wiring without changing public routes**

`router.py` obtains the shared Runtime and passes request ID, actor and model adapter through `AgentRuntimeContext`. Existing request and response models remain unchanged.

- [ ] **Step 4: Run compatibility tests before deleting legacy modules**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_service_compatibility.py tests/agent/test_runtime.py tests/agent/test_sse_contract.py -q
```

Expected: pass through new Runtime path.

- [ ] **Step 5: Delete legacy modules and imports**

Delete the five legacy modules, then search the entire repository:

```powershell
rg "build_draft_loop_graph|_clear_thread|semantic_intent|route ==|UnderstandingService|from yitu.agent.(graph|nodes|state|draft_loop|understanding)" backend/src backend/evals
```

Expected: no production/eval references. Test fixtures may not preserve legacy symbols either.

- [ ] **Step 6: Preserve useful user comments in new graph/transaction locations**

Move the intent of these current user comments into the new code where applicable:

- graph entry / conditional exit / tool-node back edge;
- grant issue → consume/create in one transaction → receipt/follow-up.

Do not preserve the trailing whitespace in the old `draft.status` assignment.

- [ ] **Step 7: Run targeted and full static verification**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent -q
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 8: Commit Task 6**

```powershell
git add -A backend/src/yitu/agent backend/tests/agent backend/src/yitu/main.py
git commit -m "重构(agent)：使用 LangGraph Runtime 替换旧编排"
```

---

### Task 7: Prove PostgreSQL Resume, Transaction Safety, and API Compatibility

**Files:**
- Create: `backend/tests/agent/test_postgres_resume.py`
- Create: `backend/tests/agent/test_confirmation_concurrency.py`
- Create: `backend/tests/agent/test_api_contract.py`
- Modify: `backend/tests/conftest.py`
- Modify: production modules only when a failing integration test identifies a real defect.

**Interfaces:**
- Consumes: real `AsyncPostgresSaver`, production Ports, FastAPI endpoints.
- Produces: executable evidence for restart recovery, stale-state rejection, one-shipment concurrency, and unchanged API contracts.

- [ ] **Step 1: Add an opt-in isolated PostgreSQL fixture**

The fixture calls `require_test_database_url()`, runs Alembic against that URL, and creates per-test users/conversations. It never calls `clean_business_data` on the development URL. If `YITU_TEST_DATABASE_URL` is absent, mark integration tests skipped with an explicit reason.

- [ ] **Step 2: Write and run the restart-resume test**

Test sequence:

1. invoke root graph until child interrupt;
2. dispose first Runtime and checkpointer pool;
3. construct a second Runtime with the same database and thread ID;
4. resume confirm;
5. assert one receipt and one shipment.

Run:

```powershell
cd backend
$env:YITU_TEST_DATABASE_URL='postgresql+asyncpg://.../yitu_agent_test'
.\.venv\Scripts\python.exe -m pytest tests/agent/test_postgres_resume.py -q
```

Expected initial RED: identifies any real persistence/wiring gap. Implement only the necessary fix, then verify GREEN.

- [ ] **Step 3: Write and run stale-fact tests**

After interrupt, mutate draft revision or quote version through the real business service. Resume confirm and assert:

- no shipment row created;
- public result requires re-quote;
- rejected grant/audit behavior remains intact.

- [ ] **Step 4: Write and run concurrent confirmation test**

Launch two Runtime resumes against the same interrupted thread or two grant-consumption attempts. Assert exactly one succeeds and the database contains one shipment for the draft.

- [ ] **Step 5: Write API contract tests**

Using ASGI transport and dependency overrides bound to the isolated database, verify:

- `POST /messages` returns `user_message` and `assistant_message`;
- `POST /messages/stream` emits `user_message`, zero or more `delta`, exactly one `done`;
- failure emits `error` and no `done`;
- current frontend payload parser remains valid;
- grant button endpoint still works and shares the same deterministic write service.

- [ ] **Step 6: Run Task 7 plus all Agent tests**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent -q
uv run ruff check src tests
uv run mypy
```

Expected: all pure tests pass; integration tests pass when the explicit test DB is configured, otherwise report skipped count separately.

- [ ] **Step 7: Commit Task 7**

```powershell
git add backend/tests/agent backend/tests/conftest.py backend/src/yitu/agent
git commit -m "测试(agent)：验证恢复与并发确认"
```

---

### Task 8: Rebuild Evals and Align Documentation with the New Architecture

**Files:**
- Modify: `backend/evals/run.py`
- Replace: `backend/evals/cases/routing.yaml`
- Modify/Create: `backend/evals/cases/{security,workflow,authorization,tool_selection,draft_extraction,rag_grounding}.yaml`
- Modify: `docs/agent.md`
- Modify: `docs/agent-rag-architecture.md`
- Modify: `docs/interview-script.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/blog-yitu-architecture.md`
- Test: `backend/tests/agent/test_evals.py`

**Interfaces:**
- Consumes: complete compiled Agent graph with fixed model/test Ports.
- Produces: reproducible deterministic eval report and documentation that no longer describes the shallow graph.

- [ ] **Step 1: Write failing eval-runner tests**

The deterministic runner must execute complete graph behavior and report literal case names, passed, failed, and total. Include cases for:

- direct answer;
- knowledge tool selection and grounded response;
- multi-tool query;
- shipment handoff;
- prompt injection refusal;
- tool budget refusal;
- interrupt confirmation;
- stale revision rejection;
- duplicate confirmation protection.

- [ ] **Step 2: Implement the new deterministic runner**

Use fixed scripted Ports and `MemorySaver`; do not call production cloud services. Online model cases live separately and require an explicit flag.

- [ ] **Step 3: Run deterministic eval and verify GREEN**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent/test_evals.py -q
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evals/run.py
```

Expected: zero failed deterministic cases.

- [ ] **Step 4: Update architecture and interview documentation**

Remove every old claim that:

- main graph is model-free shallow routing;
- `UnderstandingService` owns top-level intent routing;
- tools execute in `service.py`;
- project does not use `interrupt()`;
- checkpoint is cleared every turn;
- draft graph is the only Agent loop.

Document the 15 nodes, two ReAct loops, child State, parent checkpoint propagation, defer behavior, `KnowledgePort`, and transaction boundary.

- [ ] **Step 5: Run stale-document reference scan**

```powershell
rg "主图不碰模型|不用 LangGraph 的 interrupt|每轮.*clear_thread|唯一的 agentic loop|service.py.*编排|UnderstandingService.*意图" docs backend/evals
```

Expected: only historical migration context explicitly labeled as old architecture; no current-state claims.

- [ ] **Step 6: Run final verification suite**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/agent -q
uv run ruff check src tests evals
uv run mypy
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evals/run.py
```

Also run the frontend build because REST/SSE TypeScript contracts must remain compatible:

```powershell
cd ..\frontend
npm run build
```

- [ ] **Step 7: Commit Task 8**

```powershell
git add backend/evals backend/tests/agent docs backend/src/yitu/agent frontend
git commit -m "文档(agent)：同步新工作流架构与评测"
```

---

## Final Acceptance Checklist

- [ ] Exactly 15 named LangGraph nodes: 7 root + 8 shipment child.
- [ ] Root and child each contain a visible Agent ↔ Tools loop.
- [ ] Main Agent can autonomously make multiple allowed read-tool calls.
- [ ] Shipment Agent cannot call quote, grant, or shipment creation as model tools.
- [ ] Child `interrupt()` pauses the root thread and resumes after Runtime recreation.
- [ ] Non-confirmation text resolves pending confirmation via `defer` before a new root turn.
- [ ] Resume reloads database facts and rejects stale draft/quote versions.
- [ ] Concurrent confirmation creates exactly one shipment.
- [ ] `service.py` contains no route dispatch, model streaming, graph construction, draft loop, or confirmation execution.
- [ ] Legacy `graph.py`, `nodes.py`, `state.py`, `draft_loop.py`, and `understanding.py` are deleted with no imports.
- [ ] `knowledge` remains independent and is called through `KnowledgePort`.
- [ ] REST and SSE public contracts remain unchanged; frontend build passes.
- [ ] Pure tests never connect to a development database.
- [ ] PostgreSQL tests require a database whose name ends in `_test`.
- [ ] Ruff, mypy, Agent pytest suite, deterministic evals, and frontend build pass with fresh output.
- [ ] Architecture docs, interview script, and demo script describe only the new implementation.
