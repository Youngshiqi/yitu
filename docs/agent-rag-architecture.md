# Agent 与 RAG 模块细粒度讲解

> 本文面向研发同学，从代码级粒度拆解 `backend/src/yitu/agent` 与 `backend/src/yitu/knowledge` 两个模块。
> 每个小节都给出「实现位置 → 数据结构/关键常量 → 流程」，并尽量用 Mermaid 图表达。
> 更偏「业务白话」的版本见根目录 `overview.md`；本文与之互补，侧重真实代码与流程图的对应关系。

---

## 0. 项目结构总览

```
yitu/
├── backend/                     # FastAPI + SQLAlchemy(async) + Celery + LangGraph
│   ├── src/yitu/
│   │   ├── agent/               # ★ 本文重点：AI 对话编排与受控写操作
│   │   ├── knowledge/           # ★ 本文重点：生产 RAG（摄入 + 检索）
│   │   ├── shipments/           # 运单领域（状态机、轨迹、应用服务）
│   │   ├── addresses/           # 地址簿（查重、归一化）
│   │   ├── pricing/             # 计价（报价快照、规则版本）
│   │   ├── dispatch/            # 派单/任务
│   │   ├── identity/            # 身份与角色（JWT、权限四层校验）
│   │   ├── platform/            # 配置、数据库、幂等、审计、Outbox、错误协议
│   │   └── ...                  # sla / tracking / labels / payments / returns 等
│   ├── migrations/versions/     # Alembic 迁移
│   ├── evals/cases/             # 固定评测集（Agent 离线评测）
│   ├── scripts/                 # 冒烟/脏数据清理脚本
│   └── tests/                   # 各领域专项测试
├── frontend/                    # Vue3 + Vite + Element Plus（阶段六冻结 API 后开发）
├── docs/                        # 文档（本文 + agent.md + knowledge-rag.md + 业务规则 + PRD + 计划）
├── overview.md                  # 全项目白话讲解
└── compose.yaml                 # Docker Compose（API + Worker + PostgreSQL + Redis 等）
```

两个模块在系统中的位置（Agent 依赖 RAG，两者不反向耦合）：

```mermaid
flowchart LR
    subgraph client[客户端]
        FE[前端 Vue3]
    end
    subgraph api[FastAPI 进程]
        AR[agent/router.py]
        KR[knowledge/router.py]
    end
    subgraph agent[agent 模块]
        SVC[service.py 编排]
        G[graph.py 主路由图]
        DL[draft_loop.py 草稿子图]
        UND[understanding.py 意图理解]
        T[agent/tools/* 工具集]
        M[memory.py / grants.py]
    end
    subgraph rag[knowledge 模块]
        RET[retrieval.py 检索器]
        IDX[indexing.py 索引]
        CHK[chunking.py 分块]
        EMB[embedding.py 向量]
    end
    subgraph infra[基础设施]
        PG[(PostgreSQL + pgvector)]
        COS[(腾讯 COS)]
        MINERU[MinerU 云解析]
        QWEN[阿里云百炼 Qwen Embedding]
        CELERY[Celery Worker]
        LLM[对话模型 DeepSeek/OpenAI-compatible]
    end

    FE --> AR
    FE --> KR
    AR --> SVC --> G
    SVC --> DL
    SVC --> UND
    SVC --> T --> RET
    SVC --> M
    KR --> RET
    RET --> IDX --> CHK
    RET --> EMB
    UND --> LLM
    SVC --> LLM
    IDX --> PG
    RET --> PG
    IDX --> EMB --> QWEN
    KR --> COS
    CELERY --> MINERU
    CELERY --> COS
    CELERY --> IDX
    PG --> PGV[(pgvector)]
    CHK --> EMB
```

---

# 第一部分 · Agent 模块

## 1. 目录清单与职责

| 文件 | 职责 |
|------|------|
| `graph.py` | 装配**主路由图**（10 节点），只做安全路由，不调模型 |
| `draft_loop.py` | 装配**草稿填写子图**（agentic loop，模型 ⇄ 工具） |
| `nodes.py` | 主图节点的确定性实现 + 两道正则安全拦截 |
| `state.py` | `AgentState`（TypedDict），图执行共享状态 |
| `service.py` | `AgentConversationService`：单轮编排 `_run_turn`，把「图」与「业务」串起来 |
| `understanding.py` | 意图理解（Fast Path 正则 + Slow Path LLM） |
| `context.py` | `build_model_context` 上下文组装 + 截断 + 二次脱敏 |
| `model_adapter.py` | `ModelAdapter` Protocol + 固定/生产两个实现 |
| `models.py` | 5 张表：会话、消息、草稿、授权、记忆 |
| `drafts.py` | 草稿持久化、校验、报价前置（`DraftService`） |
| `grants.py` | HITL 一次性授权（签发/消费） |
| `memory.py` | 长期/语义记忆（增删查 + 语义召回） |
| `checkpoint_store.py` | LangGraph checkpointer 生命周期（memory / postgres 切换） |
| `privacy.py` | `redact_text` 脱敏 + 禁项检测 |
| `prompts.py` | 系统提示词、拒绝话术、知识解答/草稿 loop 专用提示词 |
| `rag_enhancements.py` | RAG 的 LLM 查询改写器 + 精排器（agent 持有 AI 实现） |
| `write_tools.py` | `AgentWriteService`：授权消费 + 创建运单同事务 |
| `schemas.py` / `sse.py` / `tracing.py` | 请求模型 / SSE 事件编码 / 追踪 |
| `tools/base.py` | `ToolContext`、`ToolResult` 统一契约 |
| `tools/*.py` | 只读工具：`knowledge` / `shipments` / `identity`；写工具：`drafts` |

## 2. 核心设计原则

1. **AI 是助手，不是决策者**：金额、权限、状态、SLA 一律由确定性业务服务裁决；AI 只做解释、建议和**受控**写操作。
2. **主图不碰模型，子图才碰模型**：主路由图（`graph.py`）纯确定性，只做安全检查 + 路由；唯一有模型自主循环的是草稿子图。
3. **两条入口共用同一服务**：AI 对话下单和表单下单最终都走 `ShipmentApplicationService.create`，不复制业务规则。
4. **纵深防御**：安全拦截在图外 `_run_turn` 和图内 `classify_intent_node` 各做一次。

## 3. 数据模型（5 张表）

```mermaid
erDiagram
    AGENT_CONVERSATIONS ||--o{ AGENT_MESSAGES : "1:N (CASCADE)"
    AGENT_CONVERSATIONS ||--o| AGENT_SHIPMENT_DRAFTS : "1:1 唯一"
    AGENT_CONVERSATIONS ||--o{ AGENT_ACTION_GRANTS : "1:N (CASCADE)"
    USERS ||--o{ AGENT_MEMORIES : "1:N"
    AGENT_SHIPMENT_DRAFTS ||--o{ AGENT_ACTION_GRANTS : "授权绑定草稿"
    QUOTE_SNAPSHOTS ||--o{ AGENT_SHIPMENT_DRAFTS : "quote_id"
    QUOTE_SNAPSHOTS ||--o{ AGENT_ACTION_GRANTS : "quote_id"

    AGENT_CONVERSATIONS {
        uuid id PK
        uuid owner_id FK
        string title
        string status "ACTIVE / WAITING_RETRY"
    }
    AGENT_MESSAGES {
        uuid id PK
        uuid conversation_id FK
        string role "user / assistant"
        text content
        jsonb envelope "trace_id/intent/route/tool_result/trace"
    }
    AGENT_SHIPMENT_DRAFTS {
        uuid id PK
        uuid conversation_id FK "唯一"
        jsonb payload "草稿字段"
        int revision "每次 update +1，授权绑定"
        string status "INCOMPLETE/READY_FOR_QUOTE/READY_FOR_CONFIRMATION/SHIPMENT_CREATED"
        jsonb missing_fields
        uuid quote_id FK
        string quote_version
    }
    AGENT_ACTION_GRANTS {
        uuid id PK
        uuid owner_id FK
        string action "CREATE_SHIPMENT"
        uuid draft_id FK
        int draft_revision "草稿版本绑定"
        uuid quote_id FK
        string quote_version "报价版本绑定"
        jsonb command_snapshot "下单参数完整快照"
        string command_hash "SHA-256 防篡改"
        string nonce "唯一防重放"
        datetime expires_at "5 分钟"
        datetime consumed_at "一次性消费"
    }
    AGENT_MEMORIES {
        uuid id PK
        uuid owner_id FK
        string memory_type "preference/instruction/profile"
        text content
        bool active "软删除"
        datetime expires_at
        vector embedding "1024 维，可空"
        string embedding_model
    }
```

## 4. 一次对话的完整生命周期

```mermaid
sequenceDiagram
    participant FE as 前端
    participant R as agent/router.py
    participant S as AgentConversationService._run_turn
    participant U as UnderstandingService
    participant G as 主路由图(graph.py)
    participant T as 工具(tools/*)
    participant LLM as 对话模型
    participant D as DB/PostgreSQL

    FE->>R: POST /{id}/messages/stream
    R->>S: stream_message()
    S->>D: 保存 user 消息 + 取 history + 取 memories
    S->>S: security_refusal() 图外第一道拦截
    S->>U: _understand()（Fast/Slow Path）
    U-->>S: UnderstandingResult{intent,confidence,slots}
    S->>S: _maybe_confirm()/_maybe_save_address() 确定性改写
    S->>G: ainvoke(initial_state)
    G-->>S: route / risk / next_action
    alt knowledge
        S->>T: KnowledgeSearchTool.execute() → 检索 RAG
        S->>LLM: stream() 依据证据生成（无证据则不调模型）
    else read_tool / address_tool / identity_tool
        S->>T: 只读工具
        S->>LLM: stream() 工具结果转自然语言
    else draft
        S->>S: _stream_draft_loop() 进入草稿子图
    else confirmation
        S->>S: _confirm_shipment() 签发+消费授权+创建运单
    else respond
        S->>LLM: stream() 普通回复（或直接返回追问）
    end
    S->>D: 保存 assistant 消息(envelope 含 trace_id)
    S-->>R: yield delta / done
    R-->>FE: SSE 逐字下发
```

## 5. 主路由图（`graph.py`）

```mermaid
flowchart TD
    START((开始)) --> load_context[load_context<br/>预算检查]
    load_context --> classify_intent[classify_intent<br/>安全拦截 + 意图→路由映射]
    classify_intent -->|route 条件| D{route_after_classification}

    D -->|knowledge| N3[knowledge<br/>next_action=SEARCH_PUBLISHED_KNOWLEDGE]
    D -->|read_tool| N4[read_tool<br/>next_action=QUERY_OWN_SHIPMENT]
    D -->|address_tool| N5[address_tool<br/>next_action=QUERY_OWN_ADDRESSES]
    D -->|identity_tool| N6[identity_tool<br/>next_action=QUERY_OWN_IDENTITY]
    D -->|draft| N7[draft<br/>next_action=UPDATE_SHIPMENT_DRAFT]
    D -->|confirmation| N8[confirmation<br/>next_action=REQUEST_EXPLICIT_CONFIRMATION]
    D -->|respond| N9[respond<br/>next_action=GENERATE_RESPONSE]
    D -->|blocked| N10[blocked<br/>next_action=REFUSE]

    N3 --> ENDN((结束))
    N4 --> ENDN
    N5 --> ENDN
    N6 --> ENDN
    N7 --> ENDN
    N8 --> ENDN
    N9 --> ENDN
    N10 --> ENDN
```

要点：

- 10 个节点 = `load_context` + `classify_intent` + 8 个终端节点。
- 终端节点**只产出 `next_action`**，不真正执行检索/查询；真正的工具调用在图跑完后由 `_run_turn` 按 `route` 分发执行。
- 条件边 `route_after_classification` 只读 `state["route"]`，未知值一律落到 `blocked`（默认拒绝）。

### 5.1 意图 → 路由映射（`nodes.py`）

| 意图 `AgentIntent` | 风险 `AgentRisk` | 路由 `AgentRoute` |
|---|---|---|
| `GENERAL_CHAT` | `LOW` | `respond` |
| `KNOWLEDGE_QUERY` | `LOW` | `knowledge` |
| `SHIPMENT_QUERY` | `PERSONAL_DATA` | `read_tool` |
| `DRAFT_UPDATE` | `WRITE_ACTION` | `draft` |
| `SENSITIVE_ACTION` | `WRITE_ACTION` | `confirmation` |
| `ADDRESS_QUERY` | `PERSONAL_DATA` | `address_tool` |
| `IDENTITY_QUERY` | `PERSONAL_DATA` | `identity_tool` |

特殊分支：`requires_confirmation == True` 或意图本身是 `SENSITIVE_ACTION` 时，无论识别结果如何，都强制路由到 `confirmation`。

## 6. 意图理解（`understanding.py`）

```mermaid
flowchart TD
    A[用户消息] --> B[preprocess_text<br/>NFKC/繁简/小写/jieba 分词]
    B --> C{fast_path 正则匹配 6 组规则}
    C -->|未命中 / 多意图冲突| E[LLM Slow Path]
    C -->|唯一命中 DRAFT_UPDATE<br/>且含查询信号| E
    C -->|唯一命中且非查询信号| F[返回 confidence=0.99<br/>recognition_path=RULE]
    E --> G[UNDERSTANDING_PROMPT 及地址标签<=50 与最近10轮历史]
    G --> H[complete_structured<br/>Function Calling→JSON Mode 降级]
    H --> I{置信度是否达标?}
    I -->|是| J[采纳<br/>recognition_path=LLM]
    I -->|否| K[降级 GENERAL_CHAT<br/>+ clarification_question<br/>recognition_path=FALLBACK]
```

Fast Path 的 6 组规则（`_FAST_PATH_RULES`）：

1. `SHIPMENT_QUERY`：查/看/问 + 运单/快递/包裹 + 状态/进度/轨迹；或 `yt` 单号 + 查询词。
2. `KNOWLEDGE_QUERY`：禁寄/限寄/能不能寄；包装/保价/赔付 + 规则/要求。
3. `DRAFT_UPDATE`：从 X 寄到 Y；重量 + 数字 + 单位；尺寸 `长x宽x高`。
4. `SENSITIVE_ACTION`：确认/立即/帮我 + 下单/创建运单/支付/退款/取消。
5. `ADDRESS_QUERY`：我的/看看/有哪些 + 地址；地址簿。
6. `IDENTITY_QUERY`：我是谁 / 我的账号/身份/角色/网点。

关键保护规则：只命中 `DRAFT_UPDATE` 但句子含「查/看/多少钱/多久」等查询信号（`_QUERY_SIGNAL`）时，放弃 Fast Path 交给 LLM，避免「查一下从北京寄到上海的运单」被误判为填草稿。

两个确定性改写（在 `service.py` 中，位于图执行前）：

- `_maybe_confirm`：草稿已报价待确认（`READY_FOR_CONFIRMATION`）且整句为确认词（`是/好的/确认/下单/可以…`）时，改写为 `SENSITIVE_ACTION`。
- `_maybe_save_address`：下单后待保存临时地址且整句为保存确认时，确定性把临时地址转正。

## 7. 草稿填写子图（`draft_loop.py`）

这是唯一的 **agentic loop**（模型自主循环）：

```mermaid
flowchart TD
    START((开始)) --> AGENT[draft_agent<br/>模型决定: 填字段 or 追问/完成]
    AGENT -->|有 tool_calls| COND{route_after_draft_agent}
    COND -->|draft_tools| TOOLS[draft_tools<br/>执行工具并回填 tool 消息]
    TOOLS --> AGENT
    COND -->|无 tool_calls| ENDN((结束))
```

- 工具**白名单**只有两个：`update_draft`（填字段）和 `save_address`（口述地址落库为临时地址）。
- 工厂函数 + 闭包注入依赖（`model` / `session` / `actor` / `addresses` / `stream_queue`），业务对象不进图状态。
- `draft_turns` 用 `Annotated[list, add]` 累积（`state.py`），每轮追加而非覆盖。

`update_draft` 的落库规则（`tools/drafts.py`）：

- 地址只接受**地址簿中唯一匹配的标签**（`_match_address_label`，多匹配即拒绝，绝不模糊选）。
- 标签命中后回填 `sender_address_id` + `origin_district_code`（或收件侧）。
- `save_address` 先按归一化五元组（用户/姓名/电话/区县/门牌）查重，命中复用，否则建 `ephemeral=True` 临时地址；解析省市区名称由 `resolve_region_by_names` 完成。

草稿状态机（`drafts.py`）：

```mermaid
stateDiagram-v2
    [*] --> INCOMPLETE
    INCOMPLETE --> READY_FOR_QUOTE : update 后 missing_fields 为空
    READY_FOR_QUOTE --> INCOMPLETE : 再次 update 引入缺失字段
    READY_FOR_QUOTE --> READY_FOR_CONFIRMATION : validate_and_quote 成功
    READY_FOR_CONFIRMATION --> SHIPMENT_CREATED : 授权消费创建运单
```

`validate_and_quote` 调用正式 `PricingService.quote`，报价绑定 `quote_id` + `quote_version`，供后续授权校验使用（幂等键 `agent-draft:{id}:revision:{rev}:quote`）。

## 8. HITL 人工确认（`grants.py`）

项目**不用** LangGraph 的 `interrupt()`，而是自研一次性授权令牌 `AgentActionGrant`。

```mermaid
sequenceDiagram
    participant FE as 前端
    participant S as AgentConversationService
    participant G as GrantService
    participant W as AgentWriteService
    participant D as PostgreSQL(行锁)

    Note over S: 草稿 READY_FOR_CONFIRMATION 且用户确认词
    S->>G: issue(conversation_id)
    G->>D: 校验草稿+报价 → 建 grant(SHA-256 快照/nonce/5分钟)
    G-->>S: GrantView
    S->>W: create_shipment(grant.id)
    W->>G: consume(grant_id)
    G->>D: SELECT ... FOR UPDATE 行锁
    G->>G: 校验 owner/action/consumed/expired/revision/quote/hash
    G-->>W: CreateShipmentCommand
    W->>W: ShipmentApplicationService.create(幂等键 agent-grant:{id})
    W-->>S: ShipmentView
```

消费校验清单（任一失败即审计并拒绝）：

| 校验项 | 失败码 |
|---|---|
| 非本人 | `403 FORBIDDEN_RESOURCE_OWNER` |
| 动作非法 | `409 AGENT_GRANT_ACTION_INVALID` |
| 已消费 | `409 AGENT_GRANT_CONSUMED` |
| 已过期 | `409 AGENT_GRANT_EXPIRED` |
| 草稿版本变化 | `409 AGENT_GRANT_DRAFT_CHANGED` |
| 报价变化 | `409 AGENT_GRANT_QUOTE_CHANGED` |
| 快照被篡改 | `409 AGENT_GRANT_SNAPSHOT_INVALID` |

安全保障：5 分钟短时效、一次性消费、草稿/报价版本绑定、`command_hash = canonical_json_sha256(snapshot)` 防篡改、`SELECT ... FOR UPDATE` 行锁防并发、幂等键防重放、全量审计。

## 9. 上下文组装与隐私（`context.py` + `privacy.py`）

`build_model_context(history, memories, tool_results)` 组装顺序（固定）：

1. `SYSTEM_PROMPT`（平台身份与行为边界，永远第一条）
2. `用户偏好：xxx；yyy`（记忆 ≤10 条）
3. `工具执行结果：…`（每个 ≤8000 字符，在 JSON 闭合边界处截断）
4. 历史消息（最近 20 轮，每条 ≤8000 字符）

全量过 `redact_text()` 二次脱敏：隐藏 `sk-`/`AKID` 密钥、JWT 令牌、11 位手机号、邮箱。

`contains_forbidden_memory()` 用于拒绝把密钥/令牌/联系方式写入长期记忆。

## 10. 模型适配器（`model_adapter.py`）

```mermaid
classDiagram
    class ModelAdapter {
        <<Protocol>>
        complete(messages) str
        complete_structured(messages, response_model) T
        complete_with_tools(messages, tools) ToolCallResult
        stream(messages) AsyncIterator[str]
        stream_with_tools(messages, tools) AsyncIterator[ToolStreamEvent]
    }
    class FixedModelAdapter {
        本地开发/测试，确定性返回
    }
    class OpenAICompatibleModelAdapter {
        DeepSeek 等 OpenAI-compatible 接口
        结构化: Function Calling → JSON Mode 降级
        流式工具调用按 index 累积分片
    }
    ModelAdapter <|.. FixedModelAdapter
    ModelAdapter <|.. OpenAICompatibleModelAdapter
```

`get_model_adapter()` 依据 `agent_model_provider` 选择 `fixed` / `openai-compatible` / `deepseek`。

## 11. 记忆系统（4 种）

| 记忆 | 存储 | 用途 | 实现位置 |
|---|---|---|---|
| 短期（会话消息） | `agent_messages` | 普通回复取 20 轮、草稿/理解取 10 轮 | `models.py` |
| 工作（草稿 loop 中间态） | LangGraph checkpointer | 草稿子图 `draft_turns` 持久化 | `checkpoint_store.py` |
| 长期（用户偏好） | `agent_memories` | 显式确认 + 脱敏 + 禁项过滤 | `memory.py` |
| 语义（按意思召回） | `agent_memories.embedding` | 余弦相似度召回，失败降级 recency | `memory.py` |

Checkpointer 后端切换（`checkpoint_store.py`）：

- `memory`（`MemorySaver`）：开发/测试，进程内，重启丢失。
- `postgres`（`AsyncPostgresSaver`）：生产/多副本，共享 PG，连接池 1~10，懒初始化 + 异步锁双检，`setup()` 幂等建表。
- `thread_id = conversation_id`；每轮草稿 loop 前 `_clear_thread()` 清空上一轮状态，避免 `add` reducer 累积。

语义记忆召回（`MemoryService.recall`）：

```mermaid
flowchart TD
    A[查询记忆] --> B{query 非空?}
    B -->|否| C[按 updated_at desc 取 10 条]
    B -->|是| D[生成查询向量]
    D -->|成功| E[cosine_distance 升序<br/>nulls_last<br/>无向量行按时间兜底]
    D -->|失败/服务不可用| C
```

写入时向量生成失败**不阻塞**记忆创建（`embedding=NULL` 降级），复用 `knowledge.embedding.get_embedding_provider`。

## 12. 流式输出机制

- 普通回复/工具回复：直接 `model.stream()`，每个增量 `yield ("delta", chunk)`，由 SSE 转发。
- 草稿子图：LangGraph 节点无法向外传数据，用 `asyncio.Queue` 桥接——`draft_agent_node` 在 `stream_with_tools` 里把每个 `delta` `put` 进队列，外层 `_stream_draft_loop` 并发 `get` 并 `yield`；图任务结束 `put(None)` 作为完成信号。

## 13. 执行预算与安全边界

预算常量（`service.py` 初始状态）：

- `max_turns = 8`、`max_tool_calls = 4`、`timeout_seconds = 30.0`。

安全拦截（`nodes.py`）两道正则：

- 提示注入：`忽略…指令`、`显示系统提示词`、`绕过权限`、`you are now` 等 → `INJECTION_REFUSAL` → `blocked`。
- 跨用户查询：`查别人的运单`、`查询其他用户` 等 → `CROSS_USER_REFUSAL` → `blocked`。

拒绝时**不向模型暴露内部匹配规则**，只输出固定话术。

---

# 第二部分 · RAG 模块

## 1. 目录清单与职责

| 文件 | 职责 |
|------|------|
| `models.py` | `KnowledgeDocument` / `KnowledgeChunk` 两表 + `DocumentStatus` 枚举 |
| `state_machine.py` | 文档状态转移白名单 + `resume_parsing` |
| `service.py` | 上传校验（PDF 魔数/加密/大小/SHA-256 去重）+ 删除 |
| `lifecycle.py` | 审核/发布/归档/停用/重新解析（`change_document_status`） |
| `router.py` | 管理与检索 REST API |
| `tasks.py` | Celery 任务链：`submit_mineru_document` / `poll_mineru_document` |
| `mineru_client.py` | MinerU v4 异步解析客户端（提交/轮询/下载） |
| `blob_store.py` | 对象存储抽象（本地 FS / 腾讯 COS S3） |
| `artifacts.py` | MinerU ZIP 产物安全检查与解压 |
| `parsers.py` | `MinerUParser` + `PyMuPDFParser`（降级） |
| `chunking.py` | `ChunkingPolicy` 结构化分块 |
| `tokenization.py` | jieba 分词（索引侧 / 查询侧 / 枚举增强） |
| `embedding.py` | `QwenEmbeddingProvider` / `DeterministicEmbedding` |
| `indexing.py` | `build_index_version` 双路索引构建 |
| `retrieval.py` | `KnowledgeRetriever` 混合检索 + 融合 + 精排 |
| `schemas.py` / `retrieval_schemas.py` | 请求/响应/证据视图 |
| `evaluation.py` | 检索评测 |

## 2. 数据模型与状态机

```mermaid
erDiagram
    KNOWLEDGE_DOCUMENTS ||--o{ KNOWLEDGE_CHUNKS : "1:N (CASCADE)"

    KNOWLEDGE_DOCUMENTS {
        uuid id PK
        string filename
        string sha256 "唯一去重"
        string object_key "COS 对象键"
        string status "UPLOADED/QUEUED/.../PUBLISHED"
        text parsed_text "MinerU Markdown 正文"
        string mineru_task_id "唯一, Worker 重启可恢复轮询"
        string markdown_artifact_key
        string result_archive_key
        uuid reviewed_by
        datetime effective_from "生效起始, 空则无下限"
        datetime effective_to "生效结束, 空则无上限"
        string category
    }
    KNOWLEDGE_CHUNKS {
        uuid id PK "uuid5(doc, version, index, content)"
        uuid document_id FK
        int index_version "版本化, 旧版本保留"
        int chunk_index
        text content
        text search_tokens "jieba 分词"
        vector embedding "1024 维, HNSW 索引"
        string embedding_model
        string title
        jsonb section_path "章节路径"
        string content_type "paragraph/table"
        int page_start "起始页, 空表示无页码标记"
        int page_end "结束页, 空表示无页码标记"
        string chunking_version
    }
```

文档生命周期状态机（`state_machine.py`）：

```mermaid
stateDiagram-v2
    [*] --> UPLOADED
    UPLOADED --> QUEUED : 上传成功自动入队
    UPLOADED --> PARSING
    QUEUED --> PARSING : Worker 提交 MinerU
    QUEUED --> PARSE_FAILED
    PARSING --> REVIEW_REQUIRED : 解析+索引完成
    PARSING --> PARSE_FAILED
    REVIEW_REQUIRED --> QUEUED : 重新解析
    REVIEW_REQUIRED --> PUBLISHED : 管理员审核后发布
    PARSE_FAILED --> QUEUED : reparse
    PUBLISHED --> ARCHIVED
    PUBLISHED --> DEACTIVATED
    PUBLISHED --> QUEUED : 重新解析
    DEACTIVATED --> QUEUED
```

只有 `PUBLISHED` 且处于生效时间范围内的文档参与检索。

## 3. 阶段一：摄入 / 索引管道

```mermaid
flowchart TD
    A[管理员 POST /documents<br/>上传 PDF] --> B[validate_pdf<br/>MIME/魔数/加密/大小/页数/SHA-256 去重]
    B --> C[store.put 存 COS 私有桶<br/>AES256]
    C --> D[status=QUEUED<br/>submit_mineru_document.delay]
    D --> E[submit_mineru_document<br/>presign_get 15 分钟签名 URL]
    E --> F[gateway.submit → MinerU task_id]
    F --> G[poll_mineru_document<br/>countdown=5, 每 5 秒轮询]
    G --> H{任务状态}
    H -->|processing| G
    H -->|done| I[download_result 下载 ZIP<br/>无认证客户端]
    I --> J[extract_mineru_archive<br/>≤200MB/≤2000文件/防路径穿越/唯一 full.md]
    J --> K[MinerUParser 解析 Markdown]
    K --> L[产物 ZIP + full.md 回存 COS]
    L --> M[build_index_version<br/>结构化分块 + 向量 + 全文索引]
    M --> N[status=REVIEW_REQUIRED]
    N --> O[管理员 review → publish]
    O --> P[PUBLISHED 参与检索]
```

错误二分处理（`mineru_client.py` / `tasks.py`）：

- 临时性（429 / 5xx / 网络）→ `MinerURetryableError` → Celery 退避重试（提交 8 次、轮询 60 次，backoff 上限 300s）。
- 永久性（4xx / 配置错误 / 响应非法）→ `MinerUPermanentError` → 标记 `PARSE_FAILED`，不重试。
- 幂等提交：`PARSING` 且已有 `mineru_task_id` 时重复投递只恢复轮询，不重复计费。

### 3.1 结构化分块（`chunking.py`）

`ChunkingPolicy(max_chars=800, overlap=100)`：

```mermaid
flowchart TD
    A[Markdown 正文] --> B[逐行扫描]
    B --> C{行类型}
    C -->|页码标记 page: N| D[记录 current_page]
    C -->|标题 #~######| E[维护 headings 章节栈<br/>flush 上一个块]
    C -->|表格 &#124;...&#124;| F[标记 block_type=table<br/>表格整体不拆]
    C -->|空行| G[flush]
    C -->|普通行| H[累积 pending]
    H --> I{块长度是否超限?}
    I -->|否| J[保持完整]
    I -->|是| K[优先在句号/换行处<br/>重叠 100 字切分]
    D --> B
    E --> B
    F --> H
    G --> B
    J --> L[TextChunk 含 title/section_path/content_type/page]
    K --> L
```

每块携带：序号、内容、当前章节标题、完整章节路径、内容类型（段落/表格）、页码范围。

### 3.2 双路索引（`indexing.py` + `embedding.py` + `tokenization.py`）

```mermaid
flowchart LR
    CHUNKS[知识块列表] --> VEC[向量索引]
    CHUNKS --> FTS[全文索引]

    VEC --> EMB[QwenEmbeddingProvider<br/>qwen3.7-text-embedding<br/>每批 20 条]
    EMB --> NORM[L2 归一化]
    NORM --> PGV[(pgvector 1024 维<br/>HNSW cosine_ops 索引)]

    FTS --> JIEBA[jieba.cut_for_search 分词<br/>含 title + section_path]
    JIEBA --> GIN[(tsvector 'simple'<br/>GIN 索引)]

    CHUNKS --> ID[uuid5 文档, 版本:序号:内容<br/>稳定 ID]
```

- 稳定 ID：`uuid5(document.id, f"{version}:{index}:{content}")`，重建同版本不产生重复身份。
- 版本化：`build_index_version` 每次新建 `version = latest + 1`，旧版本保留，检索只读最新版本，支持原子切换。
- 维度强约束：数据库 `CHECK (embedding_dimension = 1024)`，换模型必须先探测维度。

## 4. 阶段二：检索管道（`retrieval.py`）

```mermaid
flowchart TD
    A[用户查询 query] --> B[LLMQueryRewriter 改写<br/>超时 4s, 失败回退原查询]
    B --> C[tokenize_for_query<br/>jieba + 停用词过滤]
    C --> D{是否枚举型问句?}
    D -->|是| D2[追加目录锚点词 目录/指导目录]
    D -->|否| EV[生成查询向量<br/>lru_cache 512 缓存]
    D2 --> EV
    EV --> V[向量召回<br/>cosine_distance 升序<br/>召回数 40 到 160 之间]
    C --> K[关键词召回<br/>tsquery OR 连接 + ts_rank_cd<br/>召回数 40 到 160 之间]

    subgraph base[元数据过滤: PUBLISHED + 生效期 + 分类 + 最新 index_version]
        V
        K
    end

    V --> M[UNION 合并候选]
    K --> M
    M --> R[加权融合<br/>0.55*关键词分 + 0.45*向量分]
    R --> R2[分数归一化<br/>向量 1-d除以2, 关键词 rank除以rank加1]
    R2 --> R3{有精排器?}
    R3 -->|否| OUT[截断 limit]
    R3 -->|是| RR[取前 30 候选 → LLMReranker<br/>超时 6s, 每条≤280字]
    RR --> OUT
    OUT --> CITE[Evidence 证据组装<br/>标注来源/章节/页码]
```

权重常量（`retrieval.py`）：

- `KEYWORD_WEIGHT = 0.55`、`VECTOR_WEIGHT = 0.45`。
- 向量分归一化 `1 - (cosine_distance / 2)`（距离 0→1.0，距离 2→0.0）。
- 关键词分归一化 `ts_rank_cd / (ts_rank_cd + 1)`。
- 候选池 `candidate_limit = clamp(limit * 8, 40, 160)`；精排池 `RERANK_POOL_SIZE = 30`。

### 4.1 查询改写 / 精排的架构解耦

- `knowledge/retrieval.py` 只定义 `QueryRewriter` / `Reranker` 两个 Protocol（接口）。
- `agent/rag_enhancements.py` 提供 `LLMQueryRewriter` / `LLMReranker` 的 AI 实现。
- `build_rag_enhancements()` 生产模型可用时返回改写器+精排器，固定模型/未配置返回 `(None, None)`，自动退回纯融合排序。
- 两者失败/超时一律回退原始输入，**绝不阻塞检索主链路**。

## 5. 证据组装与引用格式

`Evidence`（`retrieval.py`）→ `KnowledgeCitation`（`tools/knowledge.py`）→ 文本块（`service.py::_format_knowledge_evidence`）：

```
【证据 1】《禁限寄物品目录》 禁寄物品（第3章/第12页）
内容……

【证据 2】《包装规范》 易碎品包装要求（第5页）
内容……
```

证据块注入时前置 `KNOWLEDGE_ANSWER_PROMPT`（只依据证据回答、枚举逐条列、末尾标来源、证据不足说明「未找到」）。**无证据时不调用模型**，直接返回 `KNOWLEDGE_NOT_FOUND_REPLY`，杜绝幻觉。

---

# 第三部分 · Agent × RAG 协同

知识问答的完整链路：

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as AgentConversationService
    participant UND as UnderstandingService
    participant G as 主路由图
    participant T as KnowledgeSearchTool
    participant RET as KnowledgeRetriever
    participant LLM as 对话模型
    participant PG as PostgreSQL(pgvector+GIN)

    U->>S: "电脑寄出去怎么包装"
    S->>UND: _understand()
    UND-->>S: KNOWLEDGE_QUERY + knowledge_query="电脑寄件包装要求"
    S->>G: ainvoke
    G-->>S: route=knowledge, next_action=SEARCH_PUBLISHED_KNOWLEDGE
    S->>T: KnowledgeSearchTool.execute(query)
    T->>RET: search(query)（改写→双路召回→融合→精排）
    RET->>PG: 向量 + 全文查询
    PG-->>RET: 候选 chunk
    RET-->>T: Evidence[]
    T-->>S: citations
    alt 有证据
        S->>S: _format_knowledge_evidence + KNOWLEDGE_ANSWER_PROMPT
        S->>LLM: stream() 依据证据生成
        LLM-->>S: 逐字增量
    else 无证据
        S-->>S: 直接返回「未找到相关规则」（不调模型）
    end
    S-->>U: SSE 逐字下发 + 来源标注
```

## 关键架构决策总结

| 维度 | 决策 | 位置 |
|---|---|---|
| 编排 | LangGraph 双层图：主图纯确定性路由，草稿子图才跑模型 | `graph.py` / `draft_loop.py` |
| 意图理解 | Fast Path 正则(0.99) → Slow Path LLM(≥0.6) → 降级追问 | `understanding.py` |
| HITL | 自研一次性授权令牌（5 分钟/版本绑定/SHA-256/行锁/幂等），不用 `interrupt()` | `grants.py` |
| 模型接入 | `ModelAdapter` Protocol，固定/生产两实现，结构化输出 FC→JSON 降级 | `model_adapter.py` |
| 记忆 | 短期(消息) + 工作(checkpointer) + 长期(偏好) + 语义(向量) | `models.py` / `memory.py` |
| RAG 摄入 | MinerU 异步解析 → Markdown 结构化分块 → Qwen 1024 维 + jieba 双路索引 | `tasks.py` / `chunking.py` / `indexing.py` |
| RAG 检索 | 关键词(0.55)+向量(0.45) 加权融合 → 可选 LLM 精排 | `retrieval.py` |
| 解耦 | knowledge 定义接口，agent 提供 AI 实现（改写/精排） | `rag_enhancements.py` |
| 安全 | 两道正则拦截 + 脱敏 + 预算限制 + 无证据不作答 | `nodes.py` / `privacy.py` |
| 流式 | 普通 `model.stream()`；草稿子图 `asyncio.Queue` 桥接 | `service.py` |
| 无外部组件 | 无 MCP、无 GraphRAG、无 Elasticsearch，全靠 PostgreSQL 内置能力 | — |
