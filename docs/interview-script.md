# Yitu AI 物流助手：重构后项目面试讲解稿

> 口径基于当前代码，而不是规划稿。建议先讲业务价值，再讲 AI Workflow，最后深入 RAG、记忆和 HITL。

## 一、先讲项目解决了什么问题

Yitu 是一个面向客户的物流寄件平台。传统寄件流程要求用户在多个页面之间填写地址、包裹、重量和尺寸，再单独查询规则、报价和运单状态。这个项目把这些动作收敛到了一个统一的 AI 助手入口。

用户可以直接用自然语言完成三类任务：

1. 查询已登录用户自己的运单、轨迹、地址和当前计价规则；
2. 查询禁寄品、包装要求等物流规则，答案来自已发布知识库；
3. 通过多轮对话补齐寄件草稿，获得正式报价，人工确认后创建运单。

其中最完整、也是项目重点展示的业务闭环是“对话寄件”：

```text
用户表达寄件需求
  -> 助手判断需要进入寄件流程
  -> 多轮收集并持久化寄件字段
  -> 确定性校验草稿
  -> 正式计价服务生成报价快照
  -> 暂停工作流，等待用户确认
  -> 用户明确确认
  -> 签发并消费一次性授权
  -> 调用统一运单服务创建运单
  -> 返回运单号和待支付金额
```

这里的设计原则是：LLM 负责理解、选择工具和自然语言交互；数据库、计价、权限、授权和建单由确定性服务负责。AI 不是业务规则的旁路。

当前项目没有实现“物流异常自主处置”。面试时不要把运单查询或规则问答描述成异常处置系统。

## 二、AI Workflow 全貌

### 2.1 这是怎样的 LangGraph 系统

重构后共有 **15 个 LangGraph 节点**：

- 助手主图 7 个节点：统一承接通用物流问答、本人数据查询、知识检索和寄件交接；
- 寄件子图 8 个节点：收集草稿、校验、报价、人工确认和创建运单。

它包含两个受限 ReAct 循环：

```text
主图：assistant_agent_node <-> assistant_tools_node
子图：draft_agent_node     <-> draft_tools_node
```

模型可以自主决定是否调用白名单工具、调用哪个工具，以及读取工具结果后是否继续；但它不能自行扩大工具集合，不能传入可信身份字段，也不能直接绕过确认创建运单。循环还有 `max_agent_turns=8` 和 `max_tool_calls=4` 的预算限制。

这是真正的 LangGraph Agent 编排，但不是 Deep Agents 架构。它是针对物流领域手工设计的“主图 + 专用子图 + 显式状态契约”架构，没有规划 Agent、动态子 Agent 或任务文件系统。

### 2.2 主图和子图的关系

```text
START
  -> load_context_node
  -> security_gate_node
  -> assistant_agent_node <-> assistant_tools_node
             |
             | start_shipment
             v
     shipment_workflow_node
             |
             v
       寄件子图（8 节点）
             |
             v
       finalize_turn_node
             -> END

任一显式错误 -> handle_failure_node -> END
```

主图和子图使用两个独立 State。主图不会把全部对话状态直接塞给子图，而是通过两个最小契约交换信息：

- `ShipmentHandoff`：主图交给子图的用户原话和候选寄件字段；
- `ShipmentWorkflowResult`：子图返回的状态、回复、回执或错误。

独立 State 是工作流数据结构，不等于 checkpoint。checkpoint 是对这些 State 快照、当前节点和 interrupt 状态的持久化机制。

### 2.3 两个 State 的重要属性

`AssistantState` 负责主图：

| 属性 | 作用 |
|---|---|
| `conversation_id` / `user_message` | 当前会话与本轮用户输入 |
| `messages` | 给主 Agent 使用的短期消息和工具观察 |
| `pending_tool_calls` | 等待工具节点执行的模型调用 |
| `shipment_handoff` / `shipment_result` | 主图与寄件子图的交接数据 |
| `response` / `error` | 最终回复或结构化错误 |
| `turn_count` / `tool_call_count` | 自主循环预算计数 |

`ShipmentState` 负责寄件子图：

| 属性 | 作用 |
|---|---|
| `handoff` / `messages` | 主图交接信息和草稿循环上下文 |
| `draft_progress` | 草稿状态、版本、已填快照和缺失字段 |
| `pending_tool_calls` | 等待执行的草稿工具调用 |
| `draft_ready` / `draft_validated` | 模型判断完成与确定性校验完成的分离标志 |
| `quote_progress` | 报价 ID、规则版本、草稿版本和金额 |
| `confirmation_snapshot` / `confirmation_decision` | HITL 快照与用户决定 |
| `workflow_result` / `error` | 子图输出契约或结构化错误 |
| `turn_count` / `tool_call_count` | 草稿 Agent 的循环预算 |

数据库 Session、用户对象、模型客户端等不可序列化或可信依赖不进入 State，而是通过 `AgentRuntimeContext` 注入节点。可信身份只来自已鉴权的 Runtime context。

## 三、助手主图：7 个节点

### 3.1 `load_context_node`

功能：加载本轮对话的短期上下文。

- 读取：`conversation_id`、`user_message`；
- 调用：`ConversationPort.load_history`，默认最多 20 条消息；
- 处理：规范化历史消息，如果本轮用户消息尚不在末尾则追加；
- 写回：`messages`、清零 `turn_count` 和 `tool_call_count`；
- LLM：不调用；Tool：不调用；RAG：不查询；MCP：不调用。

重要事实：当前节点没有调用 `MemoryService.recall`，所以长期记忆尚未注入新版主 Agent 上下文。

### 3.2 `security_gate_node`

功能：在模型调用前做确定性安全拦截。

- 读取：`user_message`；
- 处理：用正则识别提示词注入和跨用户运单访问表达；
- 写回：命中时生成包含 `code/message/source_node/retryable` 的 `WorkflowError`；
- 路由：安全则进入 `assistant_agent_node`，失败则进入 `handle_failure_node`；
- LLM、Tool、RAG、MCP：都不调用。

### 3.3 `assistant_agent_node`

功能：主 Agent 的“思考和行动选择”节点，同时承担意图理解。

- 读取：`messages`、`user_message`、`turn_count`；
- 提示词组装：`SYSTEM_PROMPT + 最近消息 + 工具观察`；
- 调用模型：`ModelPort.stream_with_tools`，并通过 LangGraph `stream_writer` 输出 token；
- 可见工具：`search_knowledge`、`get_own_shipment`、`list_addresses`、`get_current_identity`、`get_pricing_rules`、`start_shipment`；
- 输出：普通工具调用进入 `pending_tool_calls`；`start_shipment` 生成 `ShipmentHandoff`；无工具调用时生成 `response`；
- 路由：工具节点、寄件子图、最终持久化或失败节点。

这里没有独立的顶层 `UnderstandingService`。模型通过工具选择表达意图：查询规则就调用知识工具，查询本人运单就调用只读工具，需要寄件就发出 `start_shipment` 交接信号。

`start_shipment` 是图内 handoff 工具信号，不会进入普通工具节点，也不会直接执行建单。

### 3.4 `assistant_tools_node`

功能：执行主 Agent 选择的白名单只读工具，并把观察结果送回模型。

- 读取：`pending_tool_calls`、`messages`、`tool_call_count`；
- 参数校验：`AssistantToolCall` 严格校验工具名，并拒绝模型传入 `actor_id/user_id/conversation_id/grant_id/request_id`；
- `search_knowledge`：通过 `KnowledgePort` 进入混合检索 RAG；
- `get_own_shipment`：查询当前登录用户有权读取的运单、轨迹、费用和时效；
- `list_addresses`：读取当前用户的地址选项；
- `get_current_identity`：读取当前鉴权身份摘要；
- `get_pricing_rules`：读取当前生效的确定性计价规则；
- 写回：把结构化 `AssistantToolObservation` 作为 `role=tool` 消息追加到 `messages`；
- 路由：回到 `assistant_agent_node`，让模型基于观察继续决策或生成答案；
- LLM：本节点不直接调用；MCP：不调用。

所有这些 Tool 都是进程内 Python 工具，经 Port/Adapter 调用业务服务，不是 MCP Tool。

### 3.5 `shipment_workflow_node`

功能：主图与寄件子图的边界适配器。

- 读取：`conversation_id`、`shipment_handoff`；
- 处理：构造最小 `ShipmentState`，调用已编译寄件子图；
- 校验：要求子图返回合法 `ShipmentWorkflowResult`；
- 写回：`shipment_result` 和面向用户的 `response`；
- LLM、Tool、RAG、MCP：本节点都不直接调用。

子图不单独配置 checkpointer，而是由父图传播 Runtime、配置和 checkpoint namespace。

### 3.6 `finalize_turn_node`

功能：统一持久化成功回复。

- 读取：`response`；
- 调用：`ConversationPort.append_message`；
- 持久化：助手回复和 trace 摘要；
- LLM、Tool、RAG、MCP：都不调用；
- 路由：`END`。

### 3.7 `handle_failure_node`

功能：显式收口主图失败，而不是让每个节点各自拼错误话术。

- 读取并校验：`WorkflowError`；
- 持久化：稳定的用户可见错误、结构化错误和 trace；
- 写回：`response`；
- LLM、Tool、RAG、MCP：都不调用；
- 路由：`END`。

## 四、寄件子图：8 个节点

### 4.1 `load_draft_node`

功能：从业务数据库恢复寄件草稿事实。

- 读取：`conversation_id`、`handoff`、可能已有的子图 `messages`；
- 调用：`ShipmentWorkflowPort.load_progress`；
- 实际服务：`DraftService.get_or_create` 和 `DraftService.view`；
- 首次进入时：把 handoff 中的用户原话和候选字段加入消息；
- 写回：`draft_progress`、`messages` 和预算计数；
- LLM、RAG、MCP：不调用。

checkpoint 保存流程快照，数据库里的草稿才是业务事实源。

### 4.2 `draft_agent_node`

功能：寄件草稿的受限 ReAct Agent 节点。

- 读取：`draft_progress`、`messages`、`turn_count`；
- 提示词组装：把已填字段快照、缺失字段和地址标签使用规则填入 `DRAFT_LOOP_PROMPT`；
- 调用模型：`ModelPort.stream_with_tools`；
- 白名单工具：`inspect_draft`、`update_draft`、`save_address`；
- 有工具调用：写入 `pending_tool_calls`，进入工具节点；
- 无工具调用且仍缺字段：返回 `NEEDS_INPUT` 和自然语言追问；
- 无工具调用且字段齐全：设置 `draft_ready=True`，进入确定性校验；
- RAG、MCP：不调用。

模型只能提出草稿修改，不能自行报价、确认或创建运单。

### 4.3 `draft_tools_node`

功能：执行草稿工具并把最新数据库状态返回给模型。

- 读取：`pending_tool_calls`、`draft_progress`、`messages`、`tool_call_count`；
- 参数校验：`DraftToolCall` 白名单和可信字段拒绝规则；
- `inspect_draft`：重新读取草稿；
- `update_draft`：更新用户已经明确提供的字段；
- `save_address`：创建本次寄件使用的临时或保存地址并回填草稿；
- 每次工具后：重新 `load_progress`，避免模型基于陈旧快照继续推理；
- 写回：最新 `draft_progress` 和 `role=tool` 消息；
- 路由：回到 `draft_agent_node`；
- LLM、RAG、MCP：本节点都不调用。

### 4.4 `validate_draft_node`

功能：在报价前重新用数据库事实校验草稿完整性。

- 读取：`conversation_id`；
- 调用：`ShipmentWorkflowPort.load_progress`；
- 处理：若仍有缺失字段，返回 `NEEDS_INPUT`；否则设置 `draft_validated=True`；
- LLM、RAG、MCP：不调用。

这一步防止模型刚判断字段齐全，草稿却已被其他请求修改。

### 4.5 `create_quote_node`

功能：调用正式业务计价链路创建报价快照。

- 调用：`ShipmentWorkflowPort.validate_and_quote`；
- 实际服务：`DraftService.validate_and_quote`，内部使用正式计价服务；
- 写回：`quote_id`、`quote_version`、`draft_revision`、`total_cents`；
- LLM、RAG、MCP：不调用。

金额不是由模型计算，后续确认会绑定草稿版本和报价版本。

### 4.6 `request_confirmation_node`

功能：执行真正的 LangGraph Human-in-the-Loop 暂停。

- 调用：`prepare_confirmation` 重新读取草稿和报价，生成 `ConfirmationSnapshot`；
- 调用 LangGraph：`interrupt({...})`，负载包含草稿版本、报价 ID、报价版本、金额和摘要；
- 结果：工作流暂停，checkpoint 保存可恢复位置；
- 恢复值：`confirm`、`cancel` 或 `defer`；
- `confirm`：进入创建节点；`cancel/defer`：返回相应工作流结果并结束；
- LLM、RAG、MCP：不调用。

用户是否确认由 Runtime 对固定确认/取消词做确定性归一化，模型无权替用户授权。

### 4.7 `create_confirmed_shipment_node`

功能：消费人工确认后的受控写操作。

- 调用：唯一的 `ShipmentWorkflowPort.create_confirmed`；
- Adapter 内部：先签发 `AgentActionGrant`，再在同一数据库事务中消费授权并创建运单；
- 最终服务：`ShipmentApplicationService.create`，与普通表单入口共用业务规则；
- 写回：`ShipmentWorkflowResult(status="CREATED")` 和运单回执；
- LLM、RAG、MCP：不调用。

### 4.8 `shipment_failure_node`

功能：显式收口子图错误。

- 读取：`WorkflowError`；
- 转换：`ShipmentWorkflowResult(status="FAILED")`；
- 主图再负责统一落库；
- LLM、Tool、RAG、MCP：都不调用。

## 五、RAG：离线建库阶段

RAG 代码仍放在独立的 `knowledge` 模块中。LangGraph 不复制检索实现，而是通过 `KnowledgePort -> KnowledgeAdapter -> KnowledgeSearchTool -> KnowledgeRetriever` 调用它。

### 5.1 上传与存储

管理员上传知识文档后，系统先校验文件格式、大小、内容类型、哈希等信息，再把原文件写入私有对象存储，并在 PostgreSQL 中保存文档元数据和生命周期状态。

当前支持 PDF、Markdown、TXT 和 DOCX：

- PDF：通过 Celery 异步提交 MinerU v4 解析；
- Markdown/TXT：本地解码；
- DOCX：解析 `word/document.xml` 并保留标题层级；
- 当前生产 PDF 主链路没有自动切换 PyMuPDF 的逻辑，MinerU 永久失败会进入 `PARSE_FAILED`。

### 5.2 MinerU 异步解析

PDF 流程分成提交任务和轮询任务，`mineru_task_id` 持久化在数据库：

1. 生成短时源文件签名 URL，提交 MinerU；
2. Celery 以 5 秒起始延迟轮询；临时网络、429、5xx 走退避重试；
3. Worker 重启后可根据 `mineru_task_id` 恢复，不重复提交计费；
4. 完成后下载 ZIP，安全解压并定位唯一 `full.md`；
5. 解析后的 Markdown 和原始 ZIP 回存对象存储；
6. 进入分块和索引构建。

### 5.3 结构化分块

`ChunkingPolicy` 不是简单按固定长度硬切：

- 识别 Markdown 标题并维护 `section_path`；
- 跟踪页码范围；
- 表格尽量整体保留；
- 合并条款和枚举项，减少目录类知识被切碎；
- 超长块再按句号或换行切分，并保留 overlap；
- 每个块保存 `title/section_path/content_type/page_start/page_end`。

这些结构元数据既用于检索，也用于最终引用来源。

### 5.4 双路索引与版本

每个 chunk 同时建立两类索引：

- 语义索引：Qwen 1024 维 embedding，PostgreSQL `pgvector` + HNSW cosine；
- 关键词索引：Jieba 分词写入 `search_tokens`，PostgreSQL `tsvector` + GIN。

索引按文档版本递增。chunk ID 使用文档、版本、序号和内容生成稳定 UUID。新索引构建完成后文档进入 `REVIEW_REQUIRED`，只有审核并发布的文档才会进入在线检索；检索只使用每个文档的最新索引版本和当前有效期内的内容。

## 六、RAG：在线检索与生成阶段

### 6.1 Agent 何时触发 RAG

用户问物流规则时，`assistant_agent_node` 自主选择 `search_knowledge`，参数包含查询、可选分类和最多 5 条结果。`assistant_tools_node` 调用 `KnowledgePort`，最终进入 `KnowledgeRetriever.search`。

### 6.2 查询改写

生产模型可用时启用 `LLMQueryRewriter`：

- system prompt 要求保留专有名词、补齐物流领域表达、去掉寒暄；
- 只允许单行、最长 200 字的改写结果；
- 超时预算 4 秒；
- 失败、超时或输出非法时回退原查询，不阻塞检索。

固定模型或模型未配置时，不启用改写和精排。

### 6.3 混合召回与融合

系统对改写后的查询做 Jieba 分词，并形成两路候选：

1. 向量召回：按 pgvector cosine distance 升序；
2. 关键词召回：`to_tsvector('simple', search_tokens)` 配合 `tsquery` 和 `ts_rank_cd`。

候选规模为 `limit * 8`，最少 40、最多 160。两路候选 union 后归一化并融合：

```text
final_score = 0.45 * keyword_score + 0.55 * vector_score
```

当前权重是向量高于关键词。项目没有接入 Elasticsearch、BM25 服务、GraphRAG 或知识图谱。

### 6.4 可选 LLM 精排

配置了精排器时，融合排序先取最多 30 条候选：

- 每条只给模型最多 280 字，控制 token；
- prompt 要求输出候选索引和 0~1 分数的 JSON；
- 超时预算 6 秒；
- 解析失败或超时保持原融合顺序。

### 6.5 证据回到主 Agent

Retriever 返回文档名、章节、页码、正文和分数等证据。工具节点将其包装为 `AssistantToolObservation`，追加到 `messages`，主图再回到 `assistant_agent_node`。模型看到系统提示词、用户问题和证据后生成最终回答。

必须准确描述当前防幻觉能力：

- 已有约束：只检索已发布有效文档；证据结构化返回；系统提示词要求证据不足时明确说明，不得编造；
- 当前不足：检索为空后仍会回到模型生成回复，并非代码层“无证据就完全不调用模型”的硬短路；
- 因此面试时应称为“证据约束生成”，不要声称已经从架构上百分之百杜绝幻觉。

## 七、短期记忆、长期记忆与 Checkpoint

### 7.1 短期对话记忆

业务层短期记忆保存在 `agent_messages`：

- 每轮用户消息和助手最终回复都会落库；
- `load_context_node` 默认加载最近 20 条；
- 这使服务重启后仍能恢复最近对话，不依赖单进程内存。

执行中的 ReAct 消息、工具调用和工具观察则保存在当前图 State 中，供同一轮循环继续推理。

### 7.2 LangGraph 工作记忆

checkpointer 保存 State 快照、执行位置和 interrupt：

- 本地/测试可使用 `MemorySaver`；
- 生产默认使用 PostgreSQL `AsyncPostgresSaver`；
- `thread_id` 使用 `conversation_id`；
- 主图持有 checkpointer，子图继承父图的 checkpoint namespace；
- 删除会话时同步删除对应 checkpoint。

checkpoint 不是业务数据库。运单、草稿、报价和消息仍以 PostgreSQL 业务表为事实源，checkpoint 只负责恢复工作流。

### 7.3 长期记忆

项目已有 `agent_memories` 和 `MemoryService`：

- 类型限制为 `preference/instruction/profile`；
- 通过独立 API 显式创建、查询和停用，创建接口语义要求用户明确确认；
- 保存前拒绝密钥、令牌和联系方式等敏感内容，并进行脱敏；
- 可设置过期时间；
- 可生成 1024 维向量，按 cosine 相似度召回；
- embedding 失败时不阻塞写入，召回降级为更新时间排序。

但当前重构后的 `load_context_node` 没有调用 `MemoryService.recall`，也没有把长期记忆注入 `assistant_agent_node` 的 prompt。因此准确说法是：长期记忆存储和召回子系统已经实现，但尚未重新接入新版 LangGraph 主链路。若面试官追问，这是当前最明确的后续改进项之一。

## 八、HITL：暂停恢复与交易授权

这个项目把 HITL 分成两层，两层不能混为一谈。

### 8.1 第一层：LangGraph `interrupt`

`request_confirmation_node` 使用 `interrupt()` 暂停图：

1. 报价完成后构造不可含糊的确认快照；
2. checkpointer 保存节点位置和 State；
3. SSE/普通接口把金额和草稿摘要返回用户；
4. 下一轮 Runtime 先检查是否存在 pending interrupt；
5. 只有固定确认词或取消词才转换为 `Command(resume=...)`；
6. 其他输入先以 `defer` 恢复并结束旧确认，再作为一个新问题进入主图。

这解决的是“工作流在哪里暂停、如何跨请求恢复”。

### 8.2 第二层：`AgentActionGrant`

用户确认后，创建节点不会直接相信旧 State，而是在数据库事务内签发并立即消费一次性授权。授权绑定：

- 当前 owner；
- `CREATE_SHIPMENT` 动作；
- 草稿 ID 和 `draft_revision`；
- 报价 ID 和 `quote_version`；
- 完整建单命令快照及 SHA-256 hash；
- 随机 nonce；
- 5 分钟过期时间。

消费授权时使用 `SELECT ... FOR UPDATE` 锁住授权和草稿，并检查本人、动作、是否已消费、是否过期、草稿版本、报价版本、草稿状态和快照 hash。通过后把授权标记为已消费、草稿标记为已建单，再使用 `agent-grant:{grant_id}` 幂等键调用统一运单创建服务。

这解决的是“确认之后，敏感写操作如何防篡改、防重放、防并发重复执行”。

一句话区分：`interrupt` 是流程暂停恢复机制，`AgentActionGrant` 是交易授权机制。

## 九、没有使用的技术要主动说清楚

- **MCP：没有使用。** 当前 Tool 是本地 Python Port/Adapter，适合单体内低延迟调用；未来接外部承运商或第三方平台时可以把对应能力封装成 MCP Server，但不能把现在说成 MCP。
- **GraphRAG：没有使用。** 当前知识是文档 chunk，没有实体关系图。
- **Elasticsearch：没有使用。** 关键词全文检索由 PostgreSQL `tsvector + GIN` 完成。
- **Deep Agents：不是。** 当前是领域定制的分层 LangGraph。
- **物流异常自主处置：没有实现。** 当前是本人运单查询、物流规则问答和对话寄件闭环。

## 十、面试中的 90 秒总结

这个项目不是简单给聊天接口套一层 LangGraph。重构后，主助手和寄件流程都真正进入图：主图用受限 ReAct 循环完成工具选择和寄件 handoff，子图用第二个受限 ReAct 循环收集草稿，再经过确定性校验、正式报价、LangGraph interrupt 和一次性交易授权完成建单。

整个系统一共 15 个节点，主图和子图使用独立 State，通过稳定 DTO 交换最小信息；身份、Session 和模型等依赖通过 Runtime context 注入，避免污染 checkpoint。RAG 采用 PostgreSQL 全文检索与 pgvector 的混合召回，并带可降级的 LLM 查询改写和精排。短期对话和 checkpoint 已接入主链路，长期记忆子系统已实现但尚未重新注入新版 Agent，这是我会继续补齐的能力。

项目的核心工程思想是：把 LLM 的自主性限制在理解和工具选择上，把权限、金额、版本、确认和业务写入交给可验证的确定性系统。

## 十一、建议准备的追问

### Q1：这算自主 Agent 吗？

算受限的领域 Agent。模型可以在两个 ReAct 循环中自主选择工具、读取观察并继续决策，但工具集合、循环预算、权限来源、报价和写操作均受代码约束。它不是开放式通用 Agent。

### Q2：为什么要主图加子图？

主图处理统一助手入口和通用只读能力；寄件子图有独立状态、循环、报价和 HITL 生命周期。拆成子图可以隔离复杂状态，也便于单独测试和扩展，同时通过 handoff/result 契约避免两个 State 高耦合。

### Q3：为什么 State 中不放数据库 Session 和用户对象？

State 会进入 checkpoint，必须稳定且可序列化。Session 和用户对象既不可稳定序列化，也会扩大信任边界，所以只通过 `AgentRuntimeContext` 注入；模型参数无法伪造身份。

### Q4：为什么不用 MCP？

当前工具都在同一后端进程中，Port/Adapter 更简单、延迟更低、类型和事务边界更清晰。MCP 更适合跨进程、跨团队或第三方工具生态，不应为了展示技术而增加协议层。

### Q5：RAG 如何降级？

查询改写失败回退原查询，精排失败保留融合顺序，固定模型环境直接关闭两个增强器。检索主链路仍由 pgvector 和 PostgreSQL 全文检索完成。

### Q6：为什么 interrupt 后还要授权令牌？

interrupt 只证明流程被暂停并恢复，不能单独保证草稿和报价未变化，也不能防止授权重放。Grant 通过版本绑定、hash、过期、一次消费、行锁和幂等保护真正的交易写操作。

### Q7：当前最需要继续完善什么？

第一，把 `MemoryService.recall` 正式接入 `load_context_node` 或独立记忆节点，并限制注入数量和脱敏；第二，为知识检索空结果增加代码级确定性短路或固定回复，进一步降低无证据生成风险；第三，补齐 LangGraph Studio/LangSmith 可视化追踪和节点级评测，但不改变现有业务边界。

## 代码入口

- 主图：[`backend/src/yitu/agent/workflows/assistant_graph.py`](../backend/src/yitu/agent/workflows/assistant_graph.py)
- 寄件子图：[`backend/src/yitu/agent/workflows/shipment_graph.py`](../backend/src/yitu/agent/workflows/shipment_graph.py)
- 主图节点：[`backend/src/yitu/agent/workflow_nodes/assistant_nodes.py`](../backend/src/yitu/agent/workflow_nodes/assistant_nodes.py)
- 寄件节点：[`backend/src/yitu/agent/workflow_nodes/shipment_nodes.py`](../backend/src/yitu/agent/workflow_nodes/shipment_nodes.py)
- Runtime：[`backend/src/yitu/agent/runtime/runtime.py`](../backend/src/yitu/agent/runtime/runtime.py)
- RAG 检索：[`backend/src/yitu/knowledge/retrieval.py`](../backend/src/yitu/knowledge/retrieval.py)
- 长期记忆：[`backend/src/yitu/agent/memory.py`](../backend/src/yitu/agent/memory.py)
- 交易授权：[`backend/src/yitu/agent/grants.py`](../backend/src/yitu/agent/grants.py)
