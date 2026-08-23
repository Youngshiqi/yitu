# 驿途（Yitu）：把 AI 塞进物流系统的正确姿势——一个"受控 Agent"架构的完整拆解

> 本文基于 `backend/src/yitu/` 的真实源码，拆解驿途智能物流平台的 Agent 编排、RAG 管道、人工确认（HITL）授权与记忆系统。所有代码片段、常量、正则均摘自项目仓库，可逐行对照。

## 〇、这个项目在解决什么问题

驿途是一个完整的跨城快递履约平台：报价、下单、干线、派送、签收、退换、对账、支付，全链路有真实业务约束（状态机白名单、报价快照版本、SLA 承诺时效、幂等键防重）。在此之上叠加了两条 AI 入口：

1. **对话下单**：用户说"从公司寄一台笔记本到上海浦东"，AI 帮你把草稿填完、报价、等你确认后下单；
2. **知识问答**：用户问"充电宝能不能寄"，系统检索已发布的 PDF 规则文档（禁限寄目录、包装规范），**带引用**回答。

一条贯穿全部代码的设计红线：

> **AI 是助手不是决策者。** 它能填草稿、查运单、答疑问、记偏好；但报价由确定性计价服务算、下单必须消费一次性授权令牌、状态变更必须过状态机白名单。AI 的输出永远进不了"决策位"，只能进"建议位"。

这句话不是口号——下文每一节都会给出它落地的具体代码。

---

## 一、全局架构

```
compose.yaml 服务拓扑
├── db        PostgreSQL 16 + pgvector（业务数据 + 向量 + 全文 + LangGraph checkpoint）
├── redis     Celery broker + 结果后端
├── minio     S3 兼容对象存储（开发态知识文件）
├── api       FastAPI（uvicorn，启动时 alembic upgrade head）
└── worker    Celery（独立 yitu 队列 + beat 定时任务）
```

| 层 | 选型 | 备注 |
|---|---|---|
| Web | FastAPI（全 async） | SQLAlchemy 2.x async |
| 编排 | LangGraph | 只用其图运行时，不用 interrupt() |
| 对话模型 | DeepSeek / 任意 OpenAI-compatible | `ModelAdapter` 协议隔离 |
| 嵌入 | 百炼 `qwen3.7-text-embedding` | 1024 维，批上限 20 |
| PDF 解析 | MinerU v4 云服务 | 异步提交/轮询 |
| 对象存储 | 腾讯 COS（生产）/ 本地 FS（开发） | `blob_store.py` 抽象 |

**三个"不用"**：不用 Elasticsearch（全文检索用 PG 内置 `tsvector` + GIN）；不用独立向量库（pgvector + HNSW）；不用 MCP（工具全部进程内定义，不跨进程暴露攻击面）。能用 PostgreSQL 内置能力解决的绝不引入新组件——这换来的是数据一致性边界最小化和运维复杂度可控。

---

## 二、Agent 编排：一张"不碰模型"的主图

### 2.1 双层图结构

整个 Agent 子系统只有两个 LangGraph 图：

- **主路由图**（`graph.py`）：10 个节点，**零 LLM 调用、零工具调用、零副作用**，编译时不挂 checkpointer；
- **草稿子图**（`draft_loop.py`）：唯一的 agentic loop，LLM tool_calls 驱动的条件边 + 回边循环，编译时挂 checkpointer。

判断"是不是 Agent"的标准不在用了什么框架，而在**条件边读谁写的 state**：主图的路由函数读的是代码写入的 `state["route"]`（Workflow）；草稿子图的路由函数读的是 LLM 输出的 `tool_calls`（Agent）。所以这个系统的准确定性是：**受控工作流内嵌局部 Agentic Loop**。

### 2.2 主图装配（真实代码，`graph.py`）

```python
def build_agent_graph() -> CompiledStateGraph[...]:
    graph = StateGraph(AgentState)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("knowledge", knowledge_node)
    # ... pricing_rule / read_tool / address_tool / identity_tool
    #     / draft / confirmation / respond / blocked
    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classification,   # 纯字典查表
        {"knowledge": "knowledge", ...},
    )
    for terminal_node in (...九个终端节点...):
        graph.add_edge(terminal_node, END)
    return graph.compile()           # 无 checkpointer：主图无状态
```

关键点：终端节点**只产出 `next_action` 字符串指令，不执行任何操作**。例如 `knowledge_node` 的全部实现就是：

```python
def knowledge_node(state: AgentState) -> AgentState:
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "SEARCH_PUBLISHED_KNOWLEDGE",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查找已发布的物流规则。",
    }
```

真正执行检索的是图外的 `AgentConversationService._run_turn`——图负责"决定做什么"，service 负责"去做"。这样路由逻辑可以被单测完整覆盖（不需要 mock 任何 LLM），副作用集中在图外一处，事务边界清晰。

### 2.3 安全拦截：两道正则（真实代码，`nodes.py`）

```python
INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则|提示词)"),
    re.compile(r"(显示|泄露|输出|show|reveal|print).{0,16}(系统提示词|system prompt)",
               re.IGNORECASE),
    re.compile(r"(绕过|取消|禁用).{0,8}(权限|安全|授权|审核)"),
    re.compile(r"you are now|developer message", re.IGNORECASE),
)
CROSS_USER_PATTERNS = (
    re.compile(r"(其他|别人|别人的|任意|全部)(客户|用户)?.{0,8}运单"),
    re.compile(r"查询.{0,8}(其他|别人|任意)(客户|用户)"),
)
```

拦截执行两次：**图外** `_run_turn` 先查一次（命中则连意图理解的 LLM 都不调，直接构造 `confidence=1.0` 的拒绝意图）；**图内** `classify_intent_node` 再查一次。拒绝时只输出固定话术，**不向模型暴露内部匹配规则**——模型不知道防线的形状，就难以构造绕过话术。

一个容易忽略的细节：真正挡住越权的不是这两条正则，而是数据层的 `WHERE owner_id == actor.id`（见 2.6 节工具契约）。正则是第一道显式防线，数据层是最后兜底，中间的"理解鸿沟"是已知缺口（见第七节）。

### 2.4 意图理解：三级流水线（`understanding.py`，358 行）

**意图枚举共 8 种**：`GENERAL_CHAT / KNOWLEDGE_QUERY / PRICING_QUERY / SHIPMENT_QUERY / DRAFT_UPDATE / SENSITIVE_ACTION / ADDRESS_QUERY / IDENTITY_QUERY`。

**第 0 级：预处理与短路。** NFKC 归一 → 25 项手工繁简映射（臺→台、灣→湾…，可被 OpenCC 完整替换）→ 空白折叠 → lower → jieba 分词。`jieba.initialize()` 放在**模块加载期**，消除首次请求 0.5–1s 的词典冷启动。空串/纯标点/纯 emoji 被 `_HAS_WORD = r"[A-Za-z0-9\u4e00-\u9fff]"` 短路，直接返回低置信度闲聊，**一次 LLM 都不调**。

**第 1 级：Fast Path 正则（命中即 0.99 置信度）。** 7 条 `FastPathRule`，规则设计原则是"只收录高精度模式，宁缺毋滥"。典型规则：

```python
FastPathRule("SHIPMENT_QUERY", (
    re.compile(r"(?:查|看|问).{0,8}(?:运单|快递|包裹).{0,8}(?:状态|进度|轨迹|到哪)"),
    # \b 对 CJK 无效（汉字属于 \w），改用 ASCII 环视断言单号边界：
    re.compile(r"(?<![a-z0-9])yt[a-z0-9]{4,32}(?![a-z0-9]).{0,8}(?:查|状态|轨迹|到哪)"),
)),
```

注意第三个正则的注释——`\bYT...` 对紧邻汉字的场景不可靠，这是中文 NLP 的经典坑，项目里用 `(?<![a-z0-9])...(?![a-z0-9])` 环视替代。

**命中多个意图立即放弃**（`len(matched) != 1 → return None`），交给 LLM。还有一条关键防误判保护：

```python
# 只命中 DRAFT_UPDATE 但语句实际在询问时，放弃快速路径交给 LLM
if matched == {"DRAFT_UPDATE"} and _QUERY_SIGNAL.search(preprocessed.normalized):
    return None

_QUERY_SIGNAL = r"(查|看|问|轨迹|状态|进度|到哪|多久|预计|多少钱|费用|运费|价格)"
```

没有这条规则，"查一下从北京寄到上海的运单"会命中"从X寄到Y"的 DRAFT_UPDATE 模式，被误判为填草稿。

**第 2 级：Slow Path LLM。** 带结构化输出（Pydantic Schema 严格约束，`extra="forbid"`，区码必须 `^\d{6}$`，单号必须 `^YT[A-Z0-9]{4,32}$`），prompt 含 7 个 few-shot 示例，注入地址簿**前 50 个标签**（只给标签不给地址详情——信息最小化）和最近 10 轮历史。置信度阈值：

```python
CONFIDENCE_THRESHOLD = 0.6   # < 0.6 时改写为 GENERAL_CHAT + 追问，recognition_path="FALLBACK"
```

**确定性改写**（在图执行前）：`_maybe_confirm` 只在三个条件同时满足时把消息改写为 `SENSITIVE_ACTION`——主意图 ∈ {GENERAL_CHAT, SENSITIVE_ACTION} + 整句是确认词 + 草稿状态恰为 `READY_FOR_CONFIRMATION`。确认词表是个 frozenset：

```python
_CONFIRMATION_WORDS = frozenset(
    {"确认", "确定", "下单", "确认下单", "好的", "好", "可以", "行",
     "没问题", "就这样", "同意", "嗯", "是的"})
```

要求**整句**（去标点后）恰好等于一个确认词，"好的，我再看看"不会误触发。

### 2.5 执行预算（真实代码，`nodes.py`）

```python
def _budget_refusal(state: AgentState) -> str | None:
    started_at = state.get("execution_started_at", monotonic())
    timeout = state.get("timeout_seconds", 30.0)
    if timeout <= 0 or monotonic() - started_at > timeout:
        return TIMEOUT_REFUSAL
    if state.get("turn_count", 0) >= state.get("max_turns", 8):
        return BUDGET_REFUSAL
    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", 4):
        return BUDGET_REFUSAL
    return None
```

预算常量：**max_turns=8、max_tool_calls=4、timeout=30s**。一个精妙的区分：主图是线性路由（节点不调工具），所以只用 `_timeout_refusal` 防"卡死"；完整的 `_budget_refusal`（轮次 + 工具次数 + 超时三项）只在草稿子图使用，防止 agentic loop 失控。同一个文件里两个函数，注释明确写出了为什么不共用。

### 2.6 工具契约：身份不可伪造（`tools/base.py`，全文 31 行）

```python
@dataclass(frozen=True, slots=True)
class ToolContext:
    actor: CurrentUser      # 来自已验证 JWT 的可信身份
    session: AsyncSession

class ToolResult(BaseModel, Generic[ResultT_co]):
    tool: str
    found: bool
    data: ResultT_co | None
    message: str
```

所有工具通过 `ToolContext.actor` 获取身份——**模型无法通过工具参数传入 user_id 越权**。信息最小化落实到返回模型：运单查询的 `ShipmentReadResult` 刻意**不含地址、姓名、电话**，只有 id / 单号 / 状态 / 已付金额 / ETA / 承诺时效 / 轨迹摘要四字段；地址簿查询只返回 id/标签/区县代码；`shipment_no` 可空，为空时返回**最近一票本人运单**（`WHERE owner_id == actor.id`）。

---

## 三、草稿子图：唯一的 Agentic Loop

### 3.1 结构

```
START → draft_agent ⇄ draft_tools → END
```

`draft_agent` 节点流式调用 `stream_with_tools`，条件边 `route_after_draft_agent` 读**最后一条 assistant 消息的 tool_calls**：有 tool_calls → 进 `draft_tools` 执行并回填 → 回边再进 `draft_agent`；无 tool_calls → END。

工具白名单只有两个（spec 由 Pydantic Schema 生成，`extra="forbid"`）：

- **`update_draft`**：填字段。地址**只接受地址簿中唯一匹配的标签**——`len(matches) == 1` 才回填 `sender_address_id`，零匹配或多匹配都进 `unresolved` 提示模型追问，**绝不模糊选**。字段约束与意图层一致（区码 `^\d{6}$` 等）。
- **`save_address`**：口述新地址落库。必须问全 7 字段（角色/姓名/电话/省/市/区/详址），`resolve_region_by_names` 解析行政区划，先按归一化五元组查重复用，否则建 `ephemeral=True` 临时地址。

### 3.2 循环的终止底气

模型说"填好了"不算数。子图结束后 `_auto_quote_if_complete` 判 `missing_fields` 是否为空——**空了才走 `validate_and_quote`（调正式 `PricingService.quote`，报价绑定 `quote_id + quote_version`），不空继续追问**。模型的"主观完成判断"永远越不过确定性字段校验。草稿状态机：

```
INCOMPLETE → READY_FOR_QUOTE     （missing_fields 清空）
READY_FOR_QUOTE → READY_FOR_CONFIRMATION   （校验+报价成功）
READY_FOR_CONFIRMATION → SHIPMENT_CREATED  （授权消费建单）
```

### 3.3 流式穿透：asyncio.Queue 哨兵协议

LangGraph 节点无法向外 yield 数据，草稿子图的 token 级流式输出靠队列桥接（`service.py` 真实代码骨架）：

```python
async def _run_graph() -> dict[str, Any]:
    try:
        return await graph.ainvoke(
            loop_state,
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        # 即使图抛异常也要投递哨兵，否则外层 while 会永久阻塞。
        await queue.put(None)
```

子图内 `draft_agent` 每产出一个 delta 就 `queue.put(chunk)`；外层并发 `queue.get()` 并通过 SSE 转发，取到 `None` 哨兵即收尾。**`finally` 里投递哨兵**这个细节保证了图崩溃时外层不会死等。每轮草稿 loop 前先 `_clear_thread()` 清空 checkpoint——否则上一轮的 `draft_turns`（`Annotated[list, add]` 累积 reducer）会形成"幻觉历史"。

---

## 四、HITL：自研一次性授权令牌（AgentActionGrant）

### 4.1 为什么不用 LangGraph 的 interrupt()

`interrupt()` 依赖 checkpointer 暂存图执行中间态，适合"通用暂停-恢复"。但对话下单的确认需要绑定**业务快照**：哪个版本的草稿、哪个版本的报价、什么参数的命令。这些约束用数据库行锁 + 哈希校验实现更精确、可审计、可并发。所以项目自研了授权令牌——图内 `confirmation_node` 只产出停靠标记 `REQUEST_EXPLICIT_CONFIRMATION`，零写操作；真正签发与消费都在图外。

### 4.2 签发（真实代码，`grants.py`）

```python
async def issue(self, conversation_id: UUID, actor: CurrentUser) -> GrantView:
    draft = await self._session.scalar(
        select(AgentShipmentDraft).where(
            AgentShipmentDraft.conversation_id == conversation_id,
            AgentShipmentDraft.owner_id == actor.id,      # 本人草稿
        )
    )
    if draft is None or draft.status != "READY_FOR_CONFIRMATION":
        raise AppError("AGENT_GRANT_NOT_READY", "草稿尚未完成校验和报价", 409)
    if draft.quote_id is None or draft.quote_version is None:
        raise AppError("AGENT_GRANT_QUOTE_REQUIRED", "授权缺少有效报价", 409)
    command = await DraftService(self._session).validate(conversation_id, actor)
    snapshot = command.model_dump(mode="json")
    grant = AgentActionGrant(
        conversation_id=conversation_id,
        owner_id=actor.id,
        action=CREATE_SHIPMENT,
        draft_id=draft.id,
        draft_revision=draft.revision,       # 绑定草稿版本
        quote_id=draft.quote_id,
        quote_version=draft.quote_version,   # 绑定报价版本
        command_snapshot=snapshot,           # 完整命令快照
        command_hash=canonical_json_sha256(snapshot),   # SHA-256 防篡改
        nonce=uuid4().hex,                   # 唯一随机串
        expires_at=Clock.now() + timedelta(minutes=5),  # 5 分钟时效
    )
    ...
```

### 4.3 消费：行锁下的七重校验（真实代码骨架）

```python
async def consume(self, grant_id, actor, request_id) -> CreateShipmentCommand:
    grant = await self._session.scalar(
        select(AgentActionGrant).where(...).with_for_update()   # 行锁
    )
    try:
        if grant.owner_id != actor.id:
            raise AppError("FORBIDDEN_RESOURCE_OWNER", ..., 403)
        if grant.action != CREATE_SHIPMENT:
            raise AppError("AGENT_GRANT_ACTION_INVALID", ..., 409)
        if grant.consumed_at is not None:
            raise AppError("AGENT_GRANT_CONSUMED", "授权已经消费", 409)
        if grant.expires_at <= now:
            raise AppError("AGENT_GRANT_EXPIRED", "授权已经过期", 409)
        draft = await self._session.get(AgentShipmentDraft, grant.draft_id,
                                        with_for_update=True)    # 草稿也上锁
        if draft is None or draft.revision != grant.draft_revision:
            raise AppError("AGENT_GRANT_DRAFT_CHANGED", "草稿已变化，请重新确认", 409)
        if draft.quote_id != grant.quote_id or draft.quote_version != grant.quote_version:
            raise AppError("AGENT_GRANT_QUOTE_CHANGED", "报价已变化，请重新确认", 409)
        if draft.status != "READY_FOR_CONFIRMATION":
            raise AppError("AGENT_GRANT_DRAFT_CONSUMED", "该草稿已下单，请勿重复创建运单", 409)
        command = CreateShipmentCommand.model_validate(grant.command_snapshot)
        if canonical_json_sha256(command.model_dump(mode="json")) != grant.command_hash:
            raise AppError("AGENT_GRANT_SNAPSHOT_INVALID", "授权快照校验失败", 409)
        grant.consumed_at = now
        # 消费即终结草稿：防止同一草稿再次签发授权重复建单。
        draft.status = "SHIPMENT_CREATED"
        return command
    except AppError as error:
        await self._reject(actor, f"agent-grant:{grant_id}", error.code, request_id)
        raise   # 每次拒绝都落审计：action="agent.grant.rejected"
```

注意消费时**grant 和 draft 双行锁**：draft 单独上锁是因为"草稿 revision 变化"这个校验必须与并发的 `update_draft` 互斥，否则存在 TOCTOU 窗口。

### 4.4 授权与建单同事务（`write_tools.py`，全文 27 行）

```python
async def create_shipment(self, grant_id: UUID, actor, request_id) -> ShipmentView:
    command = await GrantService(self._session).consume(grant_id, actor, request_id)
    return await ShipmentApplicationService(self._session).create(
        command, actor,
        idempotency_key=f"agent-grant:{grant_id}",
    )
```

三重防重放叠加：令牌一次性（`consumed_at`）+ 幂等键 `agent-grant:{grant_id}`（重复请求返回首次结果）+ 草稿终结（`SHIPMENT_CREATED` 状态封锁再次签发）。**最关键的一条：AI 对话下单和表单下单最终走的是同一个 `ShipmentApplicationService.create`**——业务规则零复制，AI 入口不享有任何绕过校验的特权。

攻击者视角看这套设计：即使提示注入完全成功、模型被诱导"确认下单"，它能做的最多是签发一个授权——消费时要过七重校验，草稿或报价在 5 分钟窗口内被改动任意一项，授权立即失效。

---

## 五、RAG 摄入：从 PDF 到带血缘的双路索引

### 5.1 上传四重校验 + 去重（`service.py`）

```python
validate_pdf(data, content_type, max_bytes) -> int   # 返回页数
# 1. 超限 → 413
# 2. content_type != application/pdf → 415
# 3. 魔数非 %PDF- → 400
# 4. 含 /Encrypt（加密 PDF）→ 400
# 页数启发式：data.count(b"/Type /Page") - data.count(b"/Type /Pages")
```

SHA-256 全文哈希查重，命中即 409 `KNOWLEDGE_DOCUMENT_EXISTS` 并返回已存在的 document_id；数据库侧 `UniqueConstraint("sha256")` 兜底并发。

### 5.2 文档状态机（`state_machine.py`）

```python
_TRANSITIONS = {
    "UPLOADED": {"QUEUED", "PARSING"},
    "QUEUED": {"PARSING", "PARSE_FAILED"},
    "PARSING": {"REVIEW_REQUIRED", "PARSE_FAILED"},
    "REVIEW_REQUIRED": {"QUEUED", "PUBLISHED"},
    "PARSE_FAILED": {"QUEUED"},
    "PUBLISHED": {"ARCHIVED", "DEACTIVATED", "QUEUED"},
    "DEACTIVATED": {"QUEUED"},
    "ARCHIVED": frozenset(),   # 终态
}
```

白名单外的转移一律 409。**只有 `PUBLISHED` 且处于生效时间窗口内的文档参与检索**——"发布"和"生效"两级控制，支持定时上线/下线知识文档。`resume_parsing` 特判：已处 PARSING 且有 task_id 的重复投递**只恢复轮询，不重复提交 MinerU（不重复计费）**。

### 5.3 Celery 任务链与错误二分（`tasks.py`）

```
submit_mineru_document（autoretry_for=(MinerURetryableError,),
                       retry_backoff=True, retry_backoff_max=300, max_retries=8）
    └─ 成功后 poll_mineru_document.apply_async(countdown=5)   # 单独投递轮询
poll_mineru_document（同参数，max_retries=60）
    └─ 任务仍在 processing → raise MinerURetryableError
       → 借用 Celery 指数退避当轮询调度器（5s 起步，上限 300s）
```

错误二分贯穿整个外部调用层：

| 类别 | 判定 | 处置 |
|---|---|---|
| 临时性 | 网络错误 / 429 / 5xx | `MinerURetryableError` → 退避重试 |
| 永久性 | 其他 4xx / JSON 非法 / `code != 0` | `MinerUPermanentError` → 标记 `PARSE_FAILED`，不重试 |

一个防御细节：`_request` 抛 `httpx.RequestError` 时 `from None` 切断异常链——因为 URL 里含签名参数，异常链可能把签名泄露进日志。MinerU 下载用**独立的 HTTP 客户端**（CDN 地址、跟随重定向、不带 Bearer 头），与 API 客户端隔离。

完成链路在**同一事务**内原子完成：写入 `parsed_text` + 产物 key → `build_index_version` → 状态转 `REVIEW_REQUIRED`。

### 5.4 ZIP 产物安全（`artifacts.py`）

- 三个上限：归档 200MB、文件数 2000、**解压后总大小 200MB**（逐文件累加 `file_size`，防解压炸弹）
- Zip Slip 防御：`\`→`/` 统一，拒绝空名、绝对路径、`..` 段、首段含 `:`（Windows 盘符）
- 业务校验：必须**恰好一个** `full.md`（0 个或多个都抛错），只在内存读取不落盘

### 5.5 结构化分块：markdown-v4（`chunking.py`）

`ChunkingPolicy(max_chars=800, overlap=100)`，`version="markdown-v4"`。这不是简单的定长切分，而是面向中文物流法规文档的**语义感知切分**：

- 六组正则分别处理：页码标记（`<!-- page: N -->`）、标题层级（`#`~`######`）、**法规条号**（`第[0-9〇一二三四五六七八九十百零两]+条`，支持中文数字！）、条头引导语（"包括/包含/如下/下列"）、列举项（`一、`/`(一)`/`（一）`/`1.`/`1、`/`(1)`）、章节级 vs 子级列举
- 表格行（行首行尾都是 `|`）连续合并为 `content_type="table"` 的块，**表格永不拆散**
- 空行切分有三种例外不 flush：孤立条号行后、pending 末尾是列举项、条头带引导语——防止产生"只有条号没有正文"的碎片 chunk
- 每块携带：章节标题、完整章节路径、内容类型、页码范围

长块重叠切分的核心算法（真实代码）：

```python
def _split(self, content: str) -> list[str]:
    if len(content) <= self.max_chars:
        return [content]
    fragments, start = [], 0
    while start < len(content):
        end = min(start + self.max_chars, len(content))
        if end < len(content):
            boundary = max(
                content.rfind("。", start, end),   # 句号
                content.rfind("\n", start, end),   # 或换行
            )
            if boundary > start + self.max_chars // 2:   # 边界须过中点才生效
                end = boundary + 1
        fragments.append(content[start:end].strip())
        if end == len(content):
            break
        start = max(end - self.overlap, start + 1)   # 下一片回退 100 字重叠
    return fragments
```

优先在句号/换行处找边界回退切分，下一片起点回退 `overlap` 保证 100 字重叠。

### 5.6 双路索引与版本血缘（`indexing.py` + `models.py`）

两个数据库索引支撑混合检索（真实定义）：

```python
Index("ix_knowledge_chunks_embedding_hnsw",
      KnowledgeChunk.embedding,
      postgresql_using="hnsw",
      postgresql_ops={"embedding": "vector_cosine_ops"}),

Index("ix_knowledge_chunks_content_fts",
      func.to_tsvector(text("'simple'"), KnowledgeChunk.search_tokens),
      postgresql_using="gin"),
```

（实现注释里记了一个坑：REGCONFIG `'simple'` 必须以 SQL 字面量编译，写成绑定参数会导致建表语句不可执行。）

索引构建的几个关键设计：

- **稳定 ID**：`uuid5(document.id, f"{version}:{chunk_index}:{content}")`——同内容同版本生成相同 ID，重建索引不产生重复身份，天然幂等
- **版本化**：每次构建 `version = max(index_version) + 1`，先 delete 同版本旧 chunk 再批量插入；旧版本保留，检索只读每文档最新版本 → **原子切换**，重建期间检索不中断
- **全文索引词包含 `content + title + section_path`**——目录结构词（如"禁寄物品"这个章节名）也能命中全文检索
- **血缘持久化**：每个 chunk 记录 `tokenizer_version`（`jieba-0.42.1-search-v2`）、`embedding_model`、`embedding_dimension`、`chunking_version`，且数据库有 CheckConstraint 强制 `embedding_dimension = 1024` 和 `length(embedding_model) > 0`——换嵌入模型必须显式重建索引，不允许新旧向量混存于同一检索空间

嵌入侧（`embedding.py`）：百炼单请求上限 20 条，按批保持顺序；响应按 `item.index` 排序并校验 indexes 必须等于 `range(len(texts))`（**服务端乱序防御**）；L2 归一化用 `math.fsum` 保证浮点精度；首次响应锁定维度，后续强制一致；零向量直接报错。测试用的 `DeterministicEmbedding` 用 32 个 `sha256(counter.to_bytes(4) + text)` digest 拼出 1024 维确定向量——CI 无外网也能覆盖真实 pgvector 的维度约束。

---

## 六、RAG 检索：混合融合与"绝不阻塞主链路"

### 6.1 融合公式（真实代码与真实权重，`retrieval.py`）

```python
# 语义向量（qwen）比中文 OR 关键词检索更可靠、噪声更低，故向量权重略高；
# 关键词命中仅作为辅助信号，避免「只沾边某个高频字」的弱相关 chunk 挤占排序。
KEYWORD_WEIGHT = 0.45
VECTOR_WEIGHT = 0.55
MAX_CANDIDATES = 160
RERANK_POOL_SIZE = 30
```

> 注意：项目旧文档（`docs/agent-rag-architecture.md`）记录的是"关键词 0.55 / 向量 0.45"，与当前源码**相反**——源码注释明确解释了为什么向量权重更高。以代码为准，这也是"文档会漂移、注释跟着决策走"的一个鲜活例子。

归一化与融合：

```python
# cosine distance 范围为 0..2；全文 rank 用 rank/(rank+1) 压缩到 0..1。
vector_score = func.greatest(
    0.0, func.least(1.0, 1.0 - (vector_distance / 2.0)),
)
keyword_score = keyword_rank / (keyword_rank + 1.0)
fused_score = (KEYWORD_WEIGHT * keyword_score
               + VECTOR_WEIGHT * vector_score).label("score")
```

两个归一化都把分数压进 [0,1] 且单调：余弦距离 0 → 1.0 分、距离 2 → 0 分；`ts_rank_cd` 越大越接近 1。关键词 tsquery 用 `|`（OR）连接而非 AND——避免停用词或单字未命中导致**空召回**；排序 tiebreaker 为 `document_id + index_version.desc() + chunk_index` 保证结果稳定。

### 6.2 检索全流程

```
query → LLM 改写（超时 4s，失败回退原查询）
      → tokenize_for_query（jieba + 21 个查询侧停用词过滤）
      → 枚举型问句检测（命中「有哪些/包含哪些」等 7 个标记词）
          → 追加锚点词 "目录"/"指导目录"（让目录类 chunk 排名提升）
      → 查询向量（进程级 LRU 缓存 512 条 ≈ 2MB，命中不再请求嵌入服务）
      → 双路召回：
          向量：order_by(cosine_distance).limit(candidate_limit)
          关键词：search_vector @@ to_tsquery('simple', or_query)
                  order_by ts_rank_cd desc
          （candidate_limit = min(max(limit*8, 40), 160)）
      → base_ids 子查询统一过滤：PUBLISHED + 生效窗口 + 每文档最新 index_version
      → UNION 合并去重 → 加权融合
      → 有精排器：取前 30 交 LLM 打分（每条截 280 字，超时 6s，失败保持融合序）
         无精排器：直接截断 limit
      → Evidence 组装（含 filename/title/section_path/page/score 六位小数）
```

查询侧停用词只作用于查询不碰索引侧（`哪些/什么/的/了/吗/请问` 等 21 词）——索引侧删词会破坏召回完整性，查询侧删词只影响 tsquery 构造，这是两边规则不对称的原因。枚举锚点词表刻意排除"列出/列举"这类祈使动词，防止误伤。

### 6.3 架构解耦：knowledge 不依赖 agent

`knowledge/retrieval.py` 只定义两个 Protocol：

```python
class QueryRewriter(Protocol):
    """把口语化查询改写为检索友好的查询；失败时应回退原查询。"""
    async def rewrite(self, query: str) -> str: ...

class Reranker(Protocol):
    """对融合候选按查询相关性精排；失败时应返回原始顺序。"""
    async def rerank(self, query: str, candidates: list["Evidence"]) -> list["Evidence"]: ...
```

LLM 实现在 `agent/rag_enhancements.py`：`LLMQueryRewriter`（改写超时 4s，输出校验：空/超 200 字/含换行 → 原样返回）和 `LLMReranker`（候选编号打 0-1 分，`_JSON_OBJECT_RE = r"\{.*\}"` DOTALL 宽容提取 JSON，解析失败保持融合序，**未打分候选得 -1 沉底且 Python sort 稳定保序**）。`build_rag_enhancements()` 用 `lru_cache(maxsize=1)` 单例，fixed provider 或未配置时返回 `(None, None)`——检索器自动退回纯融合排序。

两个增强环节的失败语义统一为"**回退，绝不阻塞检索主链路**"：改写挂了用原查询，精排挂了用融合序，嵌入挂了关键词路还在。

### 6.4 无证据不作答

检索结果为空时**不调模型**，直接返回固定话术"未找到相关规则"。有证据时注入 `KNOWLEDGE_ANSWER_PROMPT`（只依据证据回答、枚举逐条列、末尾标来源、证据不足要说明），证据块格式：

```
【证据 1】《禁限寄物品目录》 禁寄物品（第3章/第12页）
内容……

【证据 2】《包装规范》 易碎品包装要求（第5页）
```

每条 `KnowledgeCitation` 携带 `document_id / filename / index_version / title / section_path / page_start / page_end / content / score`——引用**可验证**，用户可以拿着文档名和页码去核对原文。

---

## 七、四层记忆与隐私脱敏

| 层 | 存储 | 生命周期 | 关键细节 |
|---|---|---|---|
| 短期 | `agent_messages` | 永久 | 普通回复取 20 轮，草稿/理解取 10 轮；envelope 存 trace_id/intent/confidence/route/trace 摘要 |
| 工作 | LangGraph checkpointer | 单轮草稿 loop | 每轮 `_clear_thread()` 清空防累积；MemorySaver（开发）/ AsyncPostgresSaver（生产） |
| 长期 | `agent_memories` | 软删 `active=False` | type 限 preference/instruction/profile，content 1-1000 字，注入上限 10 条 |
| 语义 | `agent_memories.embedding` | 随长期记忆 | 1024 维可空列 + HNSW |

**语义召回降级链**：查询向量生成成功 → `embedding.cosine_distance(query_vector).asc().nulls_last()`（有向量按相似度，无向量按时间兜底）；生成失败或服务不可用 → 纯 recency 排序，与旧版行为完全一致。**写入时嵌入失败不阻塞**：`asyncio.to_thread(provider.embed, ...)` 任何异常 → embedding 置 NULL + warning，记忆照常落库。

**Checkpointer 后端切换**（`checkpoint_store.py`）：配置驱动；`postgresql+asyncpg://` 连接串要转换成 `postgresql://`（SQLAlchemy URL → psycopg 方言），连接池 `min_size=1, max_size=10`，`autocommit=True, prepare_threshold=0, row_factory=dict_row`；`await saver.setup()` 幂等建表；`asyncio.Lock` + 双检锁保证懒初始化只执行一次。

**隐私脱敏**（`privacy.py`，全文 24 行，四组正则）：

```python
# sk-xxx / AKIDxxx（≥12 位）      → [密钥已隐藏]
# eyJ...（JWT 头）                → [令牌已隐藏]
# (?<!\d)1[3-9]\d{9}(?!\d)        → [手机号已隐藏]
# 邮箱                            → [邮箱已隐藏]
```

一个优雅的实现技巧：**"脱敏即检测"**——`contains_forbidden_memory(v)` 直接实现为 `redact_text(v) != v`。任何会被脱敏改写的内容，就是禁止写入长期记忆的内容，两条逻辑永远不可能漂移。

上下文组装顺序固定（`context.py`）：`SYSTEM_PROMPT`（首条不可覆盖）→ 记忆前 10 条 → 工具结果（≤8000 字符，超限时在**最后一个完整 JSON 闭合边界收口**——且仅当边界超过限制的一半，否则硬截断加标记）→ 最近 20 轮历史（同样脱敏+截断）。全量过 `redact_text()` 二次脱敏后才进模型。

---

## 八、模型适配层：一套 Protocol 隔离所有厂商

```python
class ModelAdapter(Protocol):
    def complete(self, messages) -> str: ...
    def complete_structured(self, messages, response_model) -> T: ...
    def complete_with_tools(self, messages, tools) -> ToolCallResult: ...
    def stream(self, messages) -> AsyncIterator[str]: ...
    def stream_with_tools(self, messages, tools) -> AsyncIterator[ToolStreamEvent]: ...
```

三个实现细节值得展开：

1. **结构化输出三级降级**：Function Calling（`tool_choice` 强制意图分类函数，重试 2 次，兼容"忽略 tool_choice 却返回 JSON 文本"的国产厂商）→ 捕获 `APIStatusError` → JSON Mode（Schema 拼进 prompt + `response_format={"type": "json_object"}`，再试 2 次）→ 抛 `ModelUnavailableError`。任何 OpenAI 异常都折叠成这一个异常类型，**不向调用方泄漏提示词内容**。

2. **流式工具调用按 index 分片累积**：流式响应里一个 tool_call 的 arguments 是分多个 chunk 到达的，按 `index` 累积 id/name/arguments 到 `tool_acc: dict[int, dict[str, str]]`，流结束后统一 `json.loads` 组装；解析失败的调用静默丢弃而不是炸掉整轮。

3. **FixedModelAdapter**：本地/CI 用的确定性实现，structured 恒返 `GENERAL_CHAT, confidence=0.0`，工具调用恒空——全部测试不依赖外网。

模型不可用的降级：会话置 `WAITING_RETRY`，返回 503 `AGENT_MODEL_UNAVAILABLE`；空回复保护 503 `AGENT_EMPTY_RESPONSE`；报价失败给固定话术"报价暂时算不出来，稍后再试一下哦"。

---

## 九、已知缺口：诚实的漏洞清单

项目维护着一份分级漏洞文档（`docs/agent-vulnerabilities.md`），节选：

- 🔴 **提示注入拦截依赖脆弱正则**：只匹配固定短语，换说法可绕过；对角色扮演诱导、间接引用外部不可信内容无防护。缓解依赖：关键写操作不依赖提示词边界，全部走确定性校验（第四节）。
- 🔴 **跨用户查询拦截脆弱**："帮我看看张三的快递"不命中正则，会走 read_tool；真正挡越权的是 `WHERE owner_id == actor.id`，但意图层与数据层之间有"理解鸿沟"，可能产生误导性回答。
- 🟡 **长期记忆"明确确认"无代码校验**：`MemoryService.create` 只做禁项过滤+脱敏，不校验"用户确认"语义，直接调 API 可绕过。
- 🟡 **运单查询只支持一票**：数量词无槽位建模，"查最近十条"只返回最近一条。
- 🟡 **地址标签唯一匹配过严**：地址簿有多个同名标签（两个"家"）时永远匹配不上，草稿死循环追问。
- 🟢 预算常量硬编码且主图/子图重复定义；`draft_turns` 累积无上限（token 无界增长风险）。

列出这些不是为了展示完美，恰恰相反——**知道防线在哪里结束，才知道下一块砖该砌在哪里**。而"高危项全在提示词层、没有一个在数据层或事务层"这件事本身，就是对第四节那套授权设计有效性的最好验证。

---

## 十、总结：一张决策表

| 维度 | 决策 | 落点 |
|---|---|---|
| 编排 | 主图纯确定性路由（无 LLM、无 checkpointer），草稿子图唯一 agentic loop | `graph.py` / `draft_loop.py` |
| 意图 | 正则 0.99（宁缺毋滥+多命中即弃）→ LLM ≥0.6 → FALLBACK 追问 | `understanding.py` |
| HITL | 自研一次性授权令牌：5 分钟 / 草稿+报价版本双绑定 / SHA-256 快照 / grant+draft 双行锁 / 幂等键 / 全量审计，不用 `interrupt()` | `grants.py` / `write_tools.py` |
| RAG 摄入 | MinerU 异步（错误二分 + Celery 退避当轮询器）→ markdown-v4 语义切块（中文条号/表格/列举项感知）→ 双路索引 + 版本血缘 + 原子切换 | `tasks.py` / `chunking.py` / `indexing.py` |
| RAG 检索 | 向量 0.55 + 关键词 0.45 融合（归一化到 [0,1]）→ 可选 LLM 精排，全部增强环节"失败即回退，绝不阻塞主链路" | `retrieval.py` |
| 记忆 | 四层（消息/checkpointer/偏好/语义向量），每一层都有降级链 | `memory.py` |
| 隐私 | 四组正则脱敏 + "脱敏即检测" + 工具返回信息最小化 | `privacy.py` |
| 反幻觉 | 无证据不调模型，引用携带文档名/章节/页码可验证 | `tools/knowledge.py` |
| 外部依赖 | 无 MCP、无 GraphRAG、无 Elasticsearch——pgvector + PG FTS + jieba | 全局 |

如果只带走一句话：**这套系统的安全性不建立在"模型很聪明"上，而建立在"模型的每一条输出都要过确定性关卡"上**——路由是查表的、预算是数数的、授权是带哈希和行锁的、引用是带页码的。AI 在里面获得了充分的创造空间（理解口语、填草稿、写答案），但每一处通向真实资产的门，钥匙都在代码手里。

---

*源码：`backend/src/yitu/`（agent 22 个文件 / knowledge 16 个文件）｜配套文档：`docs/agent-rag-architecture.md`、`docs/agent-vulnerabilities.md`、`overview.md`*
