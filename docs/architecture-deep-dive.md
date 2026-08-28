# 一张图、两把锁：AI 物流履约平台的确定性边界设计

> 本文所有结论以当前代码为准。文中代码片段摘自仓库，类名、常量、文件路径都可直接对照源码。

## 这个项目在解决什么问题

驿途是一个完整的跨城快递履约平台：报价、下单、干线、派送、签收、退换、对账、支付，全链路有真实业务约束（状态机白名单、报价快照版本、SLA 承诺时效、幂等键防重）。在此之上叠加两条 AI 入口：

1. **对话下单**：用户说"从公司寄一台笔记本到上海浦东"，AI 帮你把草稿填完、报价、等你确认后下单；
2. **知识问答**：用户问"充电宝能不能寄"，系统检索已发布的 PDF 规则文档（禁限寄目录、包装规范），**带引用**回答。

一条贯穿全部代码的设计红线：

> **AI 是助手不是决策者。** 它能填草稿、查运单、答疑问；但报价由确定性计价服务算、下单必须消费一次性授权令牌、状态变更必须过状态机白名单。AI 的输出永远进不了"决策位"，只能进"建议位"。

这句话不是口号——下文每一节都会给出它落地的具体代码。

---

## 一、全局架构

```
compose.yaml 服务拓扑
├── db        PostgreSQL 16 + pgvector（业务数据 + 向量 + 全文 + LangGraph checkpoint）
├── redis     Celery broker + 结果后端
├── minio     S3 兼容对象存储（开发态知识文件）
├── api       FastAPI（uvicorn，启动时 alembic upgrade head）
└── worker    Celery（独立队列 + beat 定时任务）
```

| 层       | 选型                              | 备注                                    |
| -------- | --------------------------------- | --------------------------------------- |
| Web      | FastAPI（全 async）               | SQLAlchemy 2.x async                    |
| 编排     | LangGraph                         | **单张状态图**，`interrupt()` 做人工确认 |
| 对话模型 | DeepSeek / 任意 OpenAI-compatible | `ModelAdapter` Protocol 隔离            |
| 嵌入     | 百炼 `qwen3.7-text-embedding`     | 1024 维，单请求批上限 20                |
| PDF 解析 | MinerU 云服务                     | 异步提交 / 轮询                         |
| 对象存储 | 腾讯 COS（生产）/ 本地 FS（开发） | `blob_store.py` 抽象                    |

**三个"不用"**：不用 Elasticsearch（全文检索用 PG 内置 `tsvector` + GIN）；不用独立向量库（pgvector + HNSW）；不用 MCP（工具全部进程内定义，不跨进程暴露攻击面）。能用 PostgreSQL 内置能力解决的绝不引入新组件——换来数据一致性边界最小化、运维复杂度可控。

### Agent 子系统的分层

代码按职责切成几层目录，依赖方向只能从上往下：

```
agent/
├── workflow/         # 图：单张状态图装配、节点、条件路由、State 契约
│   └── nodes/        #   context / agent / shipment / final 四类节点
├── capabilities/     # 节点调用的确定性业务服务（知识检索、会话读取、寄件事务）
├── domain/           # 业务领域：草稿 DraftService、授权 GrantService、记忆、写服务
├── infrastructure/   # 外部能力：ModelAdapter、checkpointer、脱敏、RAG 增强、tracing
├── runtime/          # 图运行器、依赖注入上下文、SSE 事件映射
└── tools/            # Agent 白名单工具的 schema 与只读执行
```

关键边界：**节点（workflow）不写业务规则**，它只做三件事——读 State、调 `runtime.context` 上的服务、把结果写回 State。计价、建单、授权这些"有后果"的操作全部落在 `capabilities/` 和 `domain/` 的确定性服务里。LangGraph 只负责控制流，LLM 永远不直接写库。

---

## 二、单图编排：一张状态图装下对话与寄件

### 2.1 为什么是一张图

整个 Agent 子系统只有一个编译产物 `build_assistant_graph`（`agent/workflow/assistant_graph.py`），10 个节点：

```python
def build_assistant_graph(*, checkpointer=None):
    graph = StateGraph(AssistantState, context_schema=AgentRuntimeContext)
    graph.add_node("load_context_node", load_context_node)
    graph.add_node("security_gate_node", security_gate_node)
    graph.add_node("assistant_agent_node", assistant_agent_node)
    graph.add_node("assistant_tools_node", assistant_tools_node)
    graph.add_node("shipment_process_node", shipment_process_node)
    graph.add_node("create_quote_node", create_quote_node)
    graph.add_node("shipment_confirmation_node", shipment_confirmation_node)
    graph.add_node("create_shipment_node", create_shipment_node)
    graph.add_node("finalize_turn_node", finalize_turn_node)
    graph.add_node("handle_failure_node", handle_failure_node)

    graph.add_edge(START, "load_context_node")
    graph.add_edge("load_context_node", "security_gate_node")
    graph.add_conditional_edges("security_gate_node", security_result_route)
    graph.add_conditional_edges("assistant_agent_node", assistant_action_route)
    graph.add_conditional_edges("assistant_tools_node", assistant_tools_route)
    graph.add_conditional_edges("shipment_process_node", shipment_progress_route)
    graph.add_conditional_edges("create_quote_node", quote_route)
    graph.add_conditional_edges("shipment_confirmation_node", confirmation_route)
    graph.add_conditional_edges("create_shipment_node", creation_route)
    graph.add_edge("finalize_turn_node", END)
    graph.add_edge("handle_failure_node", END)
    return graph.compile(checkpointer=checkpointer, name="yitu_assistant")
```

判断"哪里是 Agent、哪里是工作流"，不看用了什么框架，而看**条件边读谁写的 State**：

- `assistant_agent_node → assistant_tools_node` 这条边上，路由读的是 **LLM 输出的 `tool_calls`**——这是唯一的 Agentic 部分；
- 寄件链（`shipment_process → create_quote → shipment_confirmation → create_shipment`）的路由读的是**代码写入的字段**（`missing_fields` 是否为空、`_confirmed` 是否为真）——这是纯确定性工作流。

所以这个系统的准确定性是：**单张状态图内，嵌一个由 LLM tool_calls 驱动的 Agent 分支，其余都是确定性事务节点**。寄件不是子图、没有第二个 Agent 循环——它就是同一张图上几个串联的确定性节点。这个选择的好处是：状态只有一份 `AssistantState`，断点恢复、事务边界、SSE 映射都只有一套逻辑。

### 2.2 入口的两道确定性关卡

每一轮对话都从 `load_context_node` 开始，它做一件容易被忽略但很关键的事——**重置上一轮残留的路由标记**：

```python
# 同一 thread 的 checkpoint 会跨回合保留 State；本轮入口必须清掉上轮
# 的路由标记和交易中间数据，不能因为陈旧值再次进入寄件或建单节点。
return {
    "messages": messages,
    "pending_tool_calls": [],
    "shipment_requested": False,
    "shipment_candidate_fields": {},
    "shipment_progress": {}, "quote_progress": {},
    "confirmation_snapshot": {}, "response": "", "error": {},
}
```

单图架构里 checkpointer 会让 State 跨轮次持久化，上一轮的 `shipment_requested=True` 如果不清，用户这轮只是闲聊也可能被误路由进寄件节点。入口节点把所有"交易中间态"归零，保证每轮从干净状态出发。

紧接着是 `security_gate_node`，一组纯正则的显式安全防线：

```python
_INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则|提示词)"),
    re.compile(r"(显示|泄露|输出|show|reveal|print).{0,16}(系统提示词|system prompt)", re.IGNORECASE),
    re.compile(r"(绕过|取消|禁用).{0,8}(权限|安全|授权|审核)"),
    re.compile(r"you are now|developer message", re.IGNORECASE),
)
_CROSS_USER_PATTERNS = (
    re.compile(r"(其他|别人|别人的|任意|全部)(客户|用户)?.{0,8}运单"),
    re.compile(r"查询.{0,8}(其他|别人|任意)(客户|用户)"),
)
```

命中注入或越权模式，直接产出 `WorkflowError`，路由到 `handle_failure_node` 返回固定拒绝话术，**连意图理解的 LLM 都不调用**。要强调的是：这道正则只是第一道显式防线，拒绝话术不回显匹配规则，模型看不到防线的形状；真正挡住越权的是数据层的 `WHERE owner_id == actor.id`（见 2.4）。

### 2.3 Agent 节点：让模型选工具，但写操作另走一条链

`assistant_agent_node` 流式调用模型，把系统提示词、对话历史和**白名单工具 spec** 一起发过去。工具表（`tools/registry.py`）一共 5 个：

| 工具 | 类型 | 作用 |
| ---- | ---- | ---- |
| `search_knowledge` | 只读 | 检索已发布且生效的物流规则证据 |
| `get_own_shipment` | 只读 | 读**本人**运单、轨迹、费用、时效 |
| `list_addresses` | 只读 | 读本人地址簿的最小化选项 |
| `get_pricing_rules` | 只读 | 读当前生效的确定性运费规则 |
| `start_shipment` | **触发** | 用户要寄件时，把提取到的候选字段交给寄件工作流 |

注意 `start_shipment` 的特殊性：它**不直接写库**，只是让节点在 State 里打一个标记。节点里有一条硬约束——开始寄件不能和其他工具混在同一轮：

```python
shipment_calls = [c for c in result.tool_calls if c.name == "start_shipment"]
if shipment_calls:
    if len(result.tool_calls) != 1:
        return _workflow_error("MIXED_SHIPMENT_TOOLS", "开始寄件不能与其他工具同时执行", ...)
    update["shipment_requested"] = True
    update["shipment_candidate_fields"] = args.extracted_fields
elif result.tool_calls:
    update["pending_tool_calls"] = [_tool_call_dict(c) for c in result.tool_calls]
else:
    update["response"] = result.content
```

条件边 `assistant_action_route` 据此三选一：有 `shipment_requested` 走寄件链；有 `pending_tool_calls` 走工具节点；否则收尾。**模型能决定"要不要开始寄件"，但寄件之后的每一步（报价、确认、建单）都不再由模型驱动。**

### 2.4 工具节点：只读、信息最小化、身份不可伪造

`assistant_tools_node` 执行 `pending_tool_calls`，把每个工具结果以 `role=tool` 消息回填，然后**再调一次模型**基于工具结果组织自然语言答复：

```python
for raw_call in raw_calls:
    call = AssistantToolCall.model_validate(raw_call)
    if call.name == "search_knowledge":
        evidence = await runtime.context.knowledge_search_service.search(request, actor_id=...)
    else:
        evidence = await runtime.context.assistant_read_service.execute(call, actor_id=...)
    messages.append({"role": "tool", "content": json.dumps(observation...), "tool_call_id": call.id})
# 工具执行完，用工具结果再让模型流式生成最终回复
async for chunk in runtime.context.model.stream([system, *messages]):
    runtime.stream_writer({"type": "token", "content": chunk})
```

三个安全细节：

1. **身份不可伪造**。所有服务通过 `runtime.context.actor_id`（来自已验证 JWT）拿身份，工具参数里**没有** user_id 字段，模型无法通过传参越权。数据层查询一律带 `owner_id == actor.id`。
2. **返回信息最小化**。运单读取结果 `ShipmentReadResult` 刻意只有 `shipment_no / status / paid_total_cents / eta_at` 这类履约必需字段，**不含寄收件姓名、电话、详细地址**；地址簿也只返回 id 和标签。模型拿到的信息越少，被诱导泄露的面越小。
3. **预算上限**。工具调用数受 `max_tool_calls=4`（`AgentRuntimeContext` 默认值）约束，超限直接返回预算拒绝话术，防止工具调用失控。

### 2.5 寄件事务链：模型填字段，代码做裁决

进入寄件链后，驱动权完全交给确定性节点：

```
shipment_process_node ──(缺字段)──▶ finalize_turn（追问）
        │（字段齐）
        ▼
create_quote_node ─▶ shipment_confirmation_node ──(confirm)──▶ create_shipment_node
        │（interrupt 人工确认）                     │（cancel/defer）
        ▼                                           ▼
   暂停，推确认卡片                          finalize_turn（取消/暂缓）
```

`shipment_process_node` 只做"应用本轮字段 + 重读草稿进度"，绝不报价、绝不决定下一步：

```python
progress = await runtime.context.shipment_conversation_service.apply_user_message(
    conversation_id, actor_id, state.get("shipment_candidate_fields", {})
)
response = ("请继续补充：" + "、".join(missing) + "。") if progress.missing_fields \
           else "寄件信息已齐全，正在为你生成报价。"
```

路由 `shipment_progress_route` 只看 `missing_fields`：空了才进报价节点，否则收尾追问。**模型说"填好了"不算数**——缺不缺字段是 `DraftService.missing_fields()` 对照必填清单算出来的。报价走正式计价服务，生成 `QuoteSnapshot` 并绑定 `quote_id + quote_version`（规则版本号），草稿状态机推进：

```
INCOMPLETE ──(missing_fields 清空)──▶ READY_FOR_QUOTE
READY_FOR_QUOTE ──(校验+报价成功)──▶ READY_FOR_CONFIRMATION
READY_FOR_CONFIRMATION ──(授权消费建单)──▶ SHIPMENT_CREATED
```

字段缺失时，本轮在追问后结束；用户下一条消息补充信息，会重新从图入口 `load_context_node` 跑一遍——不需要子图，也能完成"多轮收集字段"。

---

## 三、人工确认：interrupt 暂停 + 一次性授权令牌，两把锁叠加

这是整个系统最值得讲的部分。人工确认同时用了两种机制，它们解决不同问题、缺一不可：

### 3.1 第一把锁：`interrupt()` 管"暂停-恢复"

`shipment_confirmation_node` 在报价完成后调用 `interrupt()`，把图执行**冻结在这个节点**，向前端抛出确认快照：

```python
snapshot = await runtime.context.shipment_conversation_service.prepare_confirmation(
    conversation_id, actor_id
)
decision_value = interrupt({"kind": "shipment_confirmation", **snapshot.model_dump(mode="json")})
decision = ...  # resume 时拿到 {"decision": "confirm" | "cancel" | "defer"}
if decision == "confirm":
    update["shipment_requested"] = True
    update["shipment_candidate_fields"] = {"_confirmed": True}
else:
    update["response"] = "已取消本次寄件确认，不会创建运单。" if decision == "cancel" \
                         else "已暂缓本次寄件确认，你可以继续咨询其他问题。"
```

`interrupt()` 的语义是：这一轮图执行到此暂停，**局部状态由 checkpointer 持久化**，前端收到一张确认卡片。Runner（`runtime/graph_runner.py`）在下一轮用户消息到来时决定如何恢复：

```python
pending = await self._pending_interrupt(config)            # 图是否停在确认点
normalized = _normalize_decision(content)                  # "确认"/"取消" → confirm/cancel
if pending and normalized in {"confirm", "cancel"}:
    graph_input = Command(resume={"decision": normalized})  # 带着用户决定恢复图
elif pending:
    # 用户问了与确认无关的新问题：先用 defer 结束旧确认，再当普通新回合处理
    await self._drain(Command(resume={"decision": "defer"}), config, context)
    graph_input = {"conversation_id": ..., "user_message": content}
else:
    graph_input = {"conversation_id": ..., "user_message": content}
```

`conversation_id` 同时作为业务会话 ID 和 LangGraph 的 `thread_id`，因此中断态能跨请求、跨进程恢复——生产环境 checkpointer 是 `AsyncPostgresSaver`，多副本部署也能共享断点。

一个体贴的交互细节：用户在确认卡片弹出后没有回答"确认/取消"，而是问了个新问题，Runner 会先用 `Command(resume={"decision": "defer"})` **排空（drain）**旧的确认等待，再把新消息当普通回合处理——不会让用户被一张过时的确认卡片卡住。

### 3.2 第二把锁：一次性授权令牌管"业务快照防篡改"

`interrupt()` 解决了"图怎么暂停、怎么恢复"，但它不绑定业务语义。对话下单的确认需要回答一个更严格的问题：**用户确认的那一版草稿和报价，和真正下单时的草稿和报价，还是同一份吗？** 这靠数据库里的一次性授权令牌 `AgentActionGrant`（表 `agent_action_grants`）保证。

图在 `confirm` 后进入 `create_shipment_node`，它调用 `create_confirmed_shipment`——注意这里是**先签发令牌、再消费令牌建单**，全程在同一事务：

```python
async def create_confirmed_shipment(self, conversation_id, actor_id, request_id):
    grant = await GrantService(self._session).issue(conversation_id, self._actor)
    shipment = await AgentWriteService(self._session).create_shipment(
        grant.id, self._actor, request_id
    )
    ...
```

签发时把草稿版本、报价版本、完整命令快照连同哈希一起固化：

```python
grant = AgentActionGrant(
    action=CREATE_SHIPMENT,
    draft_id=draft.id,
    draft_revision=draft.revision,                      # 绑定草稿版本
    quote_id=draft.quote_id,
    quote_version=draft.quote_version,                  # 绑定报价版本
    command_snapshot=snapshot,                          # 完整建单命令快照
    command_hash=canonical_json_sha256(snapshot),       # SHA-256 防篡改
    nonce=uuid4().hex,
    expires_at=Clock.now() + timedelta(minutes=5),      # 5 分钟时效
)
```

消费时在**行锁**下做多重校验（`GrantService.consume`）：

```python
grant = (await session.scalar(
    select(AgentActionGrant).where(...).with_for_update()))   # 授权行锁
try:
    if grant.owner_id != actor.id:            raise ... 403   # 只能消费本人授权
    if grant.action != CREATE_SHIPMENT:       raise ... 409
    if grant.consumed_at is not None:         raise ... 409   # 一次性
    if grant.expires_at <= now:               raise ... 409   # 过期
    draft = await session.get(AgentShipmentDraft, grant.draft_id, with_for_update=True)
    if draft.revision != grant.draft_revision: raise ... 409  # 草稿变了
    if draft.quote_id != grant.quote_id or \
       draft.quote_version != grant.quote_version: raise ...  # 报价变了
    if draft.status != "READY_FOR_CONFIRMATION": raise ...    # 已下单
    if canonical_json_sha256(command) != grant.command_hash:  # 快照被篡改
        raise ...
    grant.consumed_at = now
    draft.status = "SHIPMENT_CREATED"                        # 消费即终结草稿
except AppError as error:
    await self._reject(actor, f"agent-grant:{grant_id}", error.code, request_id)
    raise   # 每次拒绝都落审计：action="agent.grant.rejected"
```

注意 **grant 和 draft 双行锁**：draft 单独上锁，是因为"草稿 revision 变化"这个校验必须和并发的草稿更新互斥，否则存在 TOCTOU 窗口（校验通过后、建单前草稿被改）。

### 3.3 为什么两把锁都要

- 只有 `interrupt()` 没有令牌：图能暂停恢复，但"恢复时的业务数据"和"用户确认时看到的数据"是否一致，没有数据库级保证；
- 只有令牌没有 `interrupt()`：能做一次性授权，但图执行到一半的中间态、SSE 确认卡片、跨进程恢复，都要自己造轮子。

两者叠加后，建单路径有三重防重放：**令牌一次性**（`consumed_at`）+ **幂等键** `agent-grant:{grant_id}`（重复请求返回首次结果）+ **草稿终结**（`SHIPMENT_CREATED` 状态封锁再次签发）。

而最关键的一条红线在最后一行——建单最终调用的是和表单下单**完全相同**的 `ShipmentApplicationService.create`：

```python
class AgentWriteService:
    async def create_shipment(self, grant_id, actor, request_id):
        command = await GrantService(self._session).consume(grant_id, actor, request_id)
        return await ShipmentApplicationService(self._session).create(
            command, actor, idempotency_key=f"agent-grant:{grant_id}",
        )
```

**AI 对话下单和人工表单下单走同一个履约应用服务，业务规则零复制，AI 入口不享有任何绕过校验的特权。** 即使提示注入完全成功、模型被诱导"确认下单"，它能做的最多是触发一次签发——消费时七重校验，草稿或报价在 5 分钟窗口内改动任意一项，授权立即失效。

---

## 四、RAG 摄入：从 PDF 到带血缘的双路索引

知识问答的可信，建立在"检索的是已发布、生效、可溯源的内容"上。

### 4.1 上传校验与文档状态机

PDF 上传做四重校验：超限 413、content-type 非 PDF 415、魔数非 `%PDF-` 400、加密 PDF（含 `/Encrypt`）400；再用 SHA-256 全文哈希查重，命中返回 409，数据库 `UniqueConstraint("sha256")` 兜底并发。

文档有独立状态机（`knowledge/state_machine.py`），白名单外的转移一律 409：

```
UPLOADED → QUEUED → PARSING → REVIEW_REQUIRED → PUBLISHED → ARCHIVED(终态)
                              ↘ PARSE_FAILED ↗（可重新 QUEUED）
PUBLISHED 还可转 DEACTIVATED / 重新 QUEUED
```

**只有 `PUBLISHED` 且处于生效时间窗口内的文档参与检索**——"发布"和"生效"两级控制，支持定时上线 / 下线知识。

### 4.2 MinerU 异步解析与错误二分

PDF 解析走 Celery 任务链：`submit_mineru_document` 提交后，`poll_mineru_document` 以 Celery 指数退避当轮询调度器（5s 起步、上限 300s）。外部调用统一做错误二分：

| 类别 | 判定 | 处置 |
| ---- | ---- | ---- |
| 临时性 | 网络错误 / 429 / 5xx | `RetryableError` → 退避重试 |
| 永久性 | 其他 4xx / JSON 非法 / `code != 0` | `PermanentError` → 标记 `PARSE_FAILED`，不重试 |

一个防御细节：请求层抛 `httpx.RequestError` 时用 `from None` 切断异常链——因为 URL 里含签名参数，异常链可能把签名泄露进日志。下载解析产物用**独立 HTTP 客户端**（不带 Bearer 头），与 API 客户端隔离。

### 4.3 语义感知分块与版本血缘

分块策略 `version="markdown-v4"`，`max_chars=800, overlap=100`，不是定长切分，而是面向中文物流法规的语义切分：识别标题层级、**中文法规条号**（`第[0-9〇一二三四五六七八九十百零两]+条`）、列举项（`一、`/`（一）`/`1.`）、表格行（连续 `|` 行合并为 `content_type="table"` 块，**表格永不拆散**）。长块重叠切分时优先在句号 / 换行处找边界，下一片回退 100 字重叠：

```python
if end < len(content):
    boundary = max(content.rfind("。", start, end), content.rfind("\n", start, end))
    if boundary > start + self.max_chars // 2:   # 边界须过中点才生效
        end = boundary + 1
...
start = max(end - self.overlap, start + 1)      # 下一片回退 100 字重叠
```

索引层两个关键设计：

- **稳定 ID**：`uuid5(document.id, f"{version}:{chunk_index}:{content}")`——同内容同版本生成相同 ID，重建索引幂等；
- **版本化原子切换**：每次 `version = max(index_version)+1`，旧版本保留，检索只读每文档最新版本，重建期间检索不中断。

每个 chunk 记录 `tokenizer_version`、`embedding_model`、`embedding_dimension`、`chunking_version`，并有 CheckConstraint 强制维度一致——**换嵌入模型必须显式重建索引，不允许新旧向量混存于同一检索空间**。

双路索引都在 PostgreSQL 内：向量用 pgvector **HNSW**（`vector_cosine_ops`），全文用 `to_tsvector('simple', search_tokens)` 的 **GIN** 索引。

---

## 五、RAG 检索：加权融合与"绝不阻塞主链路"

### 5.1 融合公式

双路召回后做归一化加权融合（`knowledge/retrieval.py`）：

```python
KEYWORD_WEIGHT = 0.45
VECTOR_WEIGHT  = 0.55      # 语义向量噪声更低，权重略高
MAX_CANDIDATES = 160
RERANK_POOL_SIZE = 30

vector_score  = greatest(0.0, least(1.0, 1.0 - (vector_distance / 2.0)))  # 余弦距离→[0,1]
keyword_score = keyword_rank / (keyword_rank + 1.0)                        # rank 压缩到[0,1]
fused_score   = KEYWORD_WEIGHT * keyword_score + VECTOR_WEIGHT * vector_score
```

两路分数都归一化到 [0,1] 且单调。关键词 tsquery 用 `|`（OR）连接而非 AND——避免停用词或单字未命中导致**空召回**。候选池 `candidate_limit = min(max(limit*8, 40), 160)`，统一在 base 子查询里过滤：PUBLISHED + 生效窗口 + 每文档最新 index_version。

### 5.2 增强环节全部"失败即回退"

检索链路在融合之后还有两个可选增强：LLM 查询改写、cross-encoder 精排（gte-rerank，取前 30 条、每条截 280 字）。`knowledge/retrieval.py` 只定义两个 Protocol，具体 LLM 实现在 `agent/infrastructure/rag_enhancements.py`：

```python
class QueryRewriter(Protocol):
    async def rewrite(self, query: str) -> str: ...      # 失败回退原查询
class Reranker(Protocol):
    async def rerank(self, query, candidates) -> list[Evidence]: ...  # 失败保持融合序
```

失败语义统一为"**回退，绝不阻塞检索主链路**"：改写挂了用原查询，精排挂了用融合序，嵌入挂了关键词路还在。未配置精排模型时（本地 / CI 的 fixed provider）自动退回纯融合排序。

### 5.3 无证据不作答，引用可验证

检索结果为空时**不调模型**，直接返回"未找到相关规则"的固定话术。有证据时才带着证据块调模型，证据块标注文档名、章节、页码：

```text
【证据 1】《禁限寄物品目录》 禁寄物品（第3章/第12页）
内容……
```

每条引用携带 `document_id / filename / index_version / title / section_path / page_start / page_end / score`——**引用可验证**，用户能拿文档名和页码去核对原文，这是防幻觉的落点。

---

## 六、记忆与隐私脱敏

### 6.1 持久记忆：独立能力，写入前脱敏

用户偏好通过独立的记忆 API 管理（`agent/domain/memory.py`，表 `agent_memories`），支持软删（`active=False`）、过期时间、1024 维可空向量列。写入时两道关卡：

```python
async def create(self, request, actor):
    if contains_forbidden_memory(request.content):
        raise AppError("AGENT_MEMORY_SENSITIVE", "记忆不能保存密钥、令牌或联系方式", 422)
    content = redact_text(request.content)              # 写入前再脱敏一次
    embedding, embedding_model = await self._embed_content(content)
    ...
```

向量生成失败不阻塞记忆落库：`asyncio.to_thread(provider.embed, ...)` 任何异常都降级为 `embedding=NULL`。记忆召回 `recall()` 有降级链：查询嵌入成功按 cosine 距离排序（无向量行 `NULLS LAST` 按时间兜底），嵌入失败退化为纯 recency 排序。

### 6.2 隐私脱敏："脱敏即检测"

脱敏在 `agent/infrastructure/privacy.py`，四组正则：

```python
_SECRET_PATTERNS = (
    (re.compile(r"\b(?:sk|AKID)[A-Za-z0-9_-]{12,}\b"), "[密钥已隐藏]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[令牌已隐藏]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号已隐藏]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[邮箱已隐藏]"),
)
```

一个优雅的技巧——**"脱敏即检测"**：

```python
def contains_forbidden_memory(value: str) -> bool:
    return redact_text(value) != value
```

任何会被脱敏改写的内容，就是禁止写入长期记忆的内容，两条逻辑永远不可能漂移。

模型调用前的上下文组装（`infrastructure/model_context.py`）固定顺序：系统提示词（首条不可覆盖）→ 用户偏好（前 10 条，脱敏）→ 工具结果（≤8000 字符，超限时在最后一个完整 JSON 闭合边界收口）→ 最近 20 轮历史（脱敏 + 截断），全量过一遍 `redact_text()` 才进模型。

---

## 七、模型适配层：一套 Protocol 隔离所有厂商

`infrastructure/model_adapter.py` 用一个 `ModelAdapter` Protocol 抽象对话、结构化输出、工具调用、流式四种能力，有两个实现：

- `OpenAICompatibleModelAdapter`：接 DeepSeek 等任意 OpenAI 兼容服务；
- `FixedModelAdapter`：本地 / CI 的确定性实现，结构化输出恒返回兜底意图、工具调用恒空——**全部测试不依赖外网**。

结构化输出三级降级值得一提：先试 Function Calling（`tool_choice` 强制意图分类，兼容"忽略 tool_choice 却返回 JSON 文本"的国产厂商）→ 捕获异常后降级到 JSON Mode（Schema 拼进 prompt + `response_format={"type":"json_object"}`）→ 都失败抛统一的 `ModelUnavailableError`。任何 OpenAI 异常都折叠成这一个类型，**不向调用方泄漏提示词内容**。

流式工具调用还有个分片累积问题：一个 tool_call 的 arguments 会分多个 chunk 到达，代码按 `index` 累积 id/name/arguments，流结束后统一 `json.loads` 组装；解析失败的单个调用静默丢弃，不炸掉整轮。

Checkpointer 后端也可配置切换（`infrastructure/checkpoint_store.py`）：本地 / 单测用内存 `MemorySaver`，生产用 `AsyncPostgresSaver`（连接串从 `postgresql+asyncpg://` 转成 psycopg 方言，`setup()` 幂等建表，双检锁保证懒初始化一次）。多副本部署必须用 postgres 共享断点状态。

---

## 总结：一张决策表

| 维度 | 决策 | 落点 |
| ---- | ---- | ---- |
| 编排 | **单张状态图**：一个 LLM tool_calls 驱动的 Agent 分支 + 一串确定性寄件事务节点，不做子图 | `workflow/assistant_graph.py` |
| 安全入口 | 图内 `security_gate_node` 正则拦截注入 / 越权，命中即不调 LLM；数据层 `owner_id` 兜底 | `workflow/nodes/context_nodes.py` |
| 工具 | 5 个白名单工具，4 个只读、1 个只打标记；身份取自 JWT 不可伪造，返回信息最小化 | `tools/registry.py`、`capabilities/assistant_read_service.py` |
| 人工确认 | **两把锁叠加**：`interrupt()` + Postgres checkpointer 管暂停恢复；一次性授权令牌（5 分钟 / 草稿+报价版本双绑定 / SHA-256 快照 / 双行锁 / 幂等键）管业务防篡改 | `workflow/nodes/shipment_nodes.py`、`domain/grants.py` |
| 写操作 | AI 下单与表单下单共用 `ShipmentApplicationService.create`，业务规则零复制 | `domain/shipment_write_service.py` |
| RAG 摄入 | MinerU 异步（错误二分 + Celery 退避轮询）→ markdown-v4 语义切块 → pgvector HNSW + PG FTS GIN 双路索引 + 版本血缘原子切换 | `knowledge/tasks.py`、`chunking.py`、`indexing.py` |
| RAG 检索 | 向量 0.55 + 关键词 0.45 归一化融合 → 可选 cross-encoder 精排，所有增强"失败即回退，绝不阻塞主链路" | `knowledge/retrieval.py` |
| 反幻觉 | 无证据不调模型，引用携带文档名 / 章节 / 页码可验证 | `capabilities/knowledge_search_service.py` |
| 记忆 | 独立记忆能力，写入前脱敏，向量失败降级 recency | `domain/memory.py` |
| 隐私 | 四组正则脱敏 + "脱敏即检测" + 工具返回信息最小化 | `infrastructure/privacy.py` |
| 外部依赖 | 无 MCP、无 Elasticsearch、无独立向量库——pgvector + PG FTS 一站搞定 | 全局 |

如果只带走一句话：**这套系统的安全性不建立在"模型很聪明"上，而建立在"模型的每一条输出都要过确定性关卡"上。** 路由是读代码写的 State、预算是数数的、暂停恢复有 checkpointer、授权是带哈希和行锁的、引用是带页码的、写库走的是和人工完全相同的应用服务。AI 在里面获得了充分的创造空间（理解口语、填草稿、组织答复），但每一扇通向真实资产的门，钥匙都在代码手里。
