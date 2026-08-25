# AI 物流助手项目口述材料

## 1. 先讲业务闭环

这是一个统一入口的物流助手。用户既可以问禁寄规则、查自己的运单，也可以在同一对话里完成寄件。寄件不是把模型的文本直接变成订单：模型负责理解和提取本轮明确的信息，代码负责草稿校验、计价、人工确认、授权和建单。

一次普通消息会先保存用户消息、加载最近对话、做安全检查，然后进入 Agent。Agent 可以直接回答，也可以查询知识库、本人运单、地址簿、身份或计价规则。若用户要寄件，Agent 调用 `start_shipment`，图转入确定性寄件节点。节点把字段合入数据库草稿，字段缺失就生成追问；字段完整才计价、展示确认，用户确认后再创建运单。

## 2. 工作流全貌

图只有 10 个节点：9 个正常节点和 1 个失败节点。

```text
load_context_node
-> security_gate_node
-> assistant_agent_node <-> assistant_tools_node
-> shipment_process_node
-> create_quote_node
-> shipment_confirmation_node (interrupt)
-> create_shipment_node
-> finalize_turn_node

任意受控失败 -> handle_failure_node
```

唯一的 ReAct 循环是 `assistant_agent_node <-> assistant_tools_node`。这说明模型能在白名单内自主选择只读工具、看到工具观察结果后继续决策；循环次数最多 8 次，工具调用最多 4 个，避免失控调用。寄件流程不是第二个 Agent 或子图，而是显式确定性节点链，所以更容易解释、测试和控制写操作。

主要 State 包括：`messages`（短期对话与工具观察）、`pending_tool_calls`、`turn_count`、`tool_call_count`、`shipment_candidate_fields`、`shipment_progress`、`quote_progress`、`confirmation_snapshot`、`response` 和 `error`。State 只存工作流快照；当前身份、Session、模型和服务由 Runtime 注入，不进入 checkpoint。

## 3. 节点逐个说明

`load_context_node` 读取最近 20 条当前会话消息，规范化成模型消息格式，保证当前用户消息位于末尾，并清除上轮残留的工具与寄件路由状态。它不生成答案。用户消息由 Runner 在进入图前持久化，防止重复执行图时重复写入。

`security_gate_node` 使用本地规则拦截明显的提示词泄露/越权探测模式。它不是权限校验的唯一防线：真正的数据权限仍由每个查询服务使用 Runtime 注入的当前用户身份执行。命中时写入结构化 `WorkflowError` 并进入失败节点。

`assistant_agent_node` 将系统提示词、短期消息和上一轮 `role=tool` 观察组装后调用 `model.stream_with_tools`。模型流式 token 由 LangGraph stream writer 交给 Runner。无工具调用时，节点写 `response`；只读工具调用写 `pending_tool_calls`；`start_shipment` 则写 `shipment_requested` 和经 schema 校验的候选字段。

`assistant_tools_node` 是 ReAct 的执行边。它只执行模型可见的五类只读工具：`search_knowledge`、本人运单、地址簿、当前身份、计价规则。结果转换为 `AssistantToolObservation`，以 `role=tool` 消息追加到 `messages`，然后回到 Agent。`role=tool` 的含义是向下一次模型调用明确标记“这是本次 tool_call 的观察结果”，模型据此组织最终自然语言回答。

`shipment_process_node` 调用 `ShipmentConversationService.apply_user_message`。服务把候选字段经既有白名单和 Pydantic 校验合入数据库草稿，随后重新读取草稿，得到数据库事实为准的 `missing_fields`。缺字段时节点写一段明确追问并进入收口；完整时才进入报价。下一条用户补充消息会重新从主图入口开始，但草稿从数据库继续，不会丢失。

`create_quote_node` 调用确定性的 `DraftService.validate_and_quote`，金额不由模型计算。它把报价 ID、版本、草稿版本、金额写入 `quote_progress`。

`shipment_confirmation_node` 读取当前草稿和报价形成 `confirmation_snapshot`，调用 LangGraph `interrupt()` 暂停。Runner 识别中断，持久化确认话术并按既有 SSE 契约返回。用户发“确认”时 Runner 以 `Command(resume={"decision": "confirm"})` 恢复同一 `thread_id`；取消或插入无关咨询会结束该确认等待。

`create_shipment_node` 只会在 confirm 后运行。它通过 `GrantService` 签发受当前用户、草稿和报价版本约束的一次性授权，再由写服务创建运单，并使用请求 ID 保障幂等。`finalize_turn_node` 和 `handle_failure_node` 分别持久化成功/失败助手消息，保持 REST 和 SSE 的 `user_message`、`delta`、`done`、`error` 契约不变。

## 4. RAG 细节

离线阶段仍在 `knowledge/` 模块：文档解析后按结构切片，生成向量，审核发布到可检索版本。在线阶段，`search_knowledge` 经过 `KnowledgeSearchService -> KnowledgeSearchTool -> KnowledgeRetriever`，使用 PostgreSQL 全文索引和 pgvector 做混合召回，只返回已发布且生效的证据块与引用元数据。

工具节点不直接写最终答案。它把证据作为 `role=tool` 观察返回 Agent；Agent 的下一轮模型调用带上这些证据，因此模型能引用检索内容回答。当前没有 MCP、GraphRAG 或 Deep Agents，不会把本地 Python 服务包装成不存在的协议能力。

## 5. 记忆与 HITL

短期记忆是数据库中最近会话消息，运行时加载到 `messages`。LangGraph checkpoint 保存 thread 的执行位置和中断状态，不能当业务事实。长期记忆模块可独立扩展，但当前核心闭环不依赖它，面试时不应虚构已接入。

HITL 发生在报价之后、建单之前。`interrupt()` 将图暂停，确认卡片中的草稿/报价摘要来自数据库读取。恢复时没有直接相信 checkpoint，而是由建单服务重新校验草稿、报价、授权与幂等数据。这样模型没有直接写订单的权限。

## 6. 技术取舍总结

我会把它定义为受控领域 Agent：LLM 负责理解、工具选择和自然语言输出；LangGraph 负责显式状态、受限 ReAct、条件路由和人工中断；确定性服务负责权限、字段校验、金额、报价版本和交易写入；PostgreSQL 是会话、草稿、报价、授权和运单的事实源。这样既能展示真实 LangGraph Agent，又避免把交易风险交给模型或隐藏在 `service.py` 的图外编排中。
