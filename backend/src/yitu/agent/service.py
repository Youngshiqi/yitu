"""Agent 会话持久化和模型调用服务。

本服务在受控 LangGraph 之外承担"图外编排"职责，把无状态路由图与有副作用的业务逻辑隔离开：

1. 持久化用户/助手消息与会话状态；
2. 图外做有副作用的准备：加载历史、加载身份、加载地址簿、调用 LLM 理解；
3. 把准备好的上下文通过 `_initial_graph_state` 打包为 AgentState 喂给路由图；
4. 拿到路由裁决后，按 route 分发执行具体工具/写操作/草稿 loop/自由回复；
5. 流式产出 token 增量，落库时附带可审计的 envelope（trace_id、intent、
   risk、route、tool_result 等）。

设计要点：图本身保持无状态纯路由，所有副作用都集中在本服务，便于路由层
可静态审计、可被 checkpointer 持久化而不污染业务逻辑。
"""

import asyncio
import inspect
from collections.abc import AsyncIterator
from datetime import timedelta
from time import monotonic
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import (
    assign_region_path,
    find_matching_address,
    list_addresses,
)
from yitu.agent.checkpoint_store import get_shared_checkpointer
from yitu.agent.context import build_model_context
from yitu.agent.draft_loop import build_draft_loop_graph
from yitu.agent.drafts import DraftPatch, DraftService, DraftView
from yitu.agent.grants import GrantService
from yitu.agent.graph import build_agent_graph
from yitu.agent.memory import MemoryService
from yitu.agent.model_adapter import ModelAdapter, ModelMessage, ModelUnavailableError
from yitu.agent.models import (
    AgentActionGrant,
    AgentConversation,
    AgentMessage,
    AgentShipmentDraft,
)
from yitu.agent.nodes import security_refusal
from yitu.agent.privacy import redact_text
from yitu.agent.prompts import (
    KNOWLEDGE_ANSWER_PROMPT,
    KNOWLEDGE_NOT_FOUND_REPLY,
    SYSTEM_PROMPT,
)
from yitu.agent.schemas import AgentTurnView, DraftAddressCreate, MessageView
from yitu.agent.state import AgentState
from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.agent.tools.identity import AddressBookTool, IdentityTool
from yitu.agent.tools.knowledge import (
    KnowledgeCitation,
    KnowledgeSearchInput,
    KnowledgeSearchTool,
)
from yitu.agent.tools.pricing import PricingRuleTool
from yitu.agent.tools.shipments import ShipmentReadInput, ShipmentReadTool
from yitu.agent.tracing import AgentTrace
from yitu.agent.understanding import (
    DraftCandidate,
    UnderstandingResult,
    UnderstandingService,
    is_confirmation_word,
    is_save_address_word,
    preprocess_text,
)
from yitu.agent.write_tools import AgentWriteService
from yitu.identity.service import CurrentUser
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.pricing.models import QuoteSnapshot
from yitu.shipments.service import ShipmentView


async def _clear_thread(checkpointer: Any, thread_id: str) -> None:
    """清空指定 thread 的 checkpoint，让每轮草稿 loop 从干净状态开始。

    草稿子图带 checkpointer 用于跨节点状态传递；如果不清理，下一轮会读到
    上一轮残留的 draft_turns，导致模型看到"自己已经填过字段"的幻觉历史。

    MemorySaver 提供同步 delete_thread；AsyncPostgresSaver 提供 adelete_thread，
    优先走异步实现，两者都不存在时静默跳过。
    """
    async_delete = getattr(checkpointer, "adelete_thread", None)
    if callable(async_delete):
        await async_delete(thread_id)
        return
    delete = getattr(checkpointer, "delete_thread", None)
    if not callable(delete):
        return
    result = delete(thread_id)
    if inspect.isawaitable(result):
        await result


class AgentConversationService:
    """维护用户隔离的会话历史，并协调可替换模型适配器。"""

    def __init__(self, session: AsyncSession, checkpointer: Any = None) -> None:
        self._session = session
        # None 表示运行期解析共享 checkpointer，由 checkpoint_store 决定后端。
        self._checkpointer = checkpointer

    async def create(
        self, actor: CurrentUser, *, title: str | None = None
    ) -> AgentConversation:
        now = Clock.now()
        conversation = AgentConversation(
            owner_id=actor.id,
            title=title,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self._session.add(conversation)
        await self._session.commit()
        return conversation

    async def list_conversations(
        self, actor: CurrentUser
    ) -> list[AgentConversation]:
        statement = (
            select(AgentConversation)
            .where(
                AgentConversation.owner_id == actor.id,
                exists().where(
                    AgentMessage.conversation_id == AgentConversation.id
                ),
            )
            .order_by(AgentConversation.updated_at.desc(), AgentConversation.id)
        )
        return list[AgentConversation]((await self._session.scalars(statement)).all())

    async def get_owned(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> AgentConversation:
        conversation = await self._session.get(AgentConversation, conversation_id)
        if conversation is None or conversation.owner_id != actor.id:
            # 统一返回不存在，避免通过 ID 探测其他用户会话。
            raise AppError(
                code="AGENT_CONVERSATION_NOT_FOUND",
                message="Agent 会话不存在",
                status_code=404,
            )
        return conversation

    async def list_messages(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> list[AgentMessage]:
        await self.get_owned(conversation_id, actor)
        return await self._load_messages(conversation_id)

    async def send_message(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        model: ModelAdapter,
    ) -> AgentTurnView:
        """非流式单轮：收集共享编排产出的事件，组装为一次完整往返。"""
        user_view: MessageView | None = None
        assistant_view: MessageView | None = None
        async for event, payload in self._run_turn(
            conversation_id, actor, content, model
        ):
            if event == "user_message":
                user_view = MessageView.model_validate(payload)
            elif event == "done":
                assistant_view = MessageView.model_validate(payload)
        if user_view is None or assistant_view is None:
            raise AppError(
                code="AGENT_TURN_INCOMPLETE",
                message="Agent 未产生完整往返结果",
                status_code=500,
            )
        return AgentTurnView(
            user_message=user_view,
            assistant_message=assistant_view,
        )

    async def _run_turn(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        model: ModelAdapter,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """共享单轮编排：保存用户消息、理解、路由、执行工具、生成并保存回复。

        产出 (event, payload) 序列（user_message / delta / done），供非流式收集或
        流式转发；错误通过 AppError 抛出，由端点层决定呈现为 HTTP 错误码还是 SSE
        error 事件。
        """
        # —— 阶段一：持久化用户消息，并把会话状态推到 ACTIVE ——
        conversation = await self.get_owned(conversation_id, actor)
        trace = AgentTrace()
        trace.record("message.received", role="user")
        now = Clock.now()
        user_message = AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content=content,
            envelope=None,
            created_at=now,
        )
        self._session.add(user_message)
        if not conversation.title:
            conversation.title = _conversation_title(content)
        conversation.updated_at = now
        await self._session.commit()
        yield (
            "user_message",
            MessageView.model_validate(user_message).model_dump(mode="json"),
        )

        # —— 阶段二：图外上下文准备 ——
        # 加载会话历史、召回长期记忆、做安全前置拦截、调 LLM 理解语义意图。
        # 这里所有副作用都不会进图：图拿到的是已经算好的 AgentState。
        history = await self._load_messages(conversation.id)
        memories = await self._load_memories(actor.id, query=content)
        refusal = security_refusal(preprocess_text(content).normalized)
        if refusal is not None:
            # 安全前置拦截命中：跳过 LLM 理解，直接构造拒绝意图。
            # addresses 留空——此分支不会进 draft，不需要地址簿。
            understanding = UnderstandingResult(
                intents=[refusal[0]],
                primary_intent=refusal[0],
                confidence=1.0,
                draft=DraftCandidate(),
            )
            addresses: list[Address] = []
        else:
            try:
                # 调 LLM 做结构化意图理解；后续两个 _maybe_* 是确定性规则改写，
                # 在 LLM 意图基础上判断"是否在确认下单/是否要保存临时地址"。
                understanding, addresses = await self._understand(
                    model, history, content, actor
                )
                understanding = await self._maybe_confirm(
                    conversation.id, actor, content, understanding
                )
                understanding = await self._maybe_save_address(
                    conversation.id, actor, content, understanding
                )
            except ModelUnavailableError as error:
                conversation.status = "WAITING_RETRY"
                conversation.updated_at = Clock.now()
                await self._session.commit()
                raise AppError(
                    code="AGENT_MODEL_UNAVAILABLE",
                    message="AI 理解服务暂时不可用，会话消息已保存，请稍后重试",
                    status_code=503,
                ) from error
        # —— 阶段三：把图外准备好的上下文喂给无状态路由图 ——
        # _initial_graph_state 是图外→图内的唯一受控入口；图执行后返回
        # 路由裁决（intent/risk/route/next_action），不带任何业务结果。
        graph_result = await build_agent_graph().ainvoke(
            self._initial_graph_state(
                conversation.id, actor, content, history, understanding
            )
        )
        trace.record(
            "graph.routed",
            route=graph_result.get("route"),
            intent=graph_result.get("intent"),
            risk=graph_result.get("risk"),
        )

        # —— 阶段四：按路由裁决分发执行 ——
        # 图只决定"做什么"，本块负责"怎么做"：调具体工具、跑草稿 loop、
        # 触发写操作或让模型自由回复。每个分支把回复片段追加到 reply_parts，
        # 流式分支还会边产边 yield delta 让用户看到逐字输出。
        route = graph_result.get("route")
        tool_result: ToolResult[BaseModel] | None = None
        pending_address: dict[str, object] | None = None
        # 把 ORM 历史记录转成模型可吃的 ModelMessage，后续工具/回复复用。
        history_messages = [
            ModelMessage(role=item.role, content=item.content) for item in history
        ]
        reply_parts: list[str] = []
        streamed = False
        try:
            # 知识检索：RAG 查已发布物流规则，找到证据才让模型作答，否则返回固定兜底。
            if route == "knowledge":
                # 启动 RAG 检索：调 KnowledgeSearchTool 查已发布物流规则
                tool_result = await KnowledgeSearchTool().execute(
                    KnowledgeSearchInput(
                        query=understanding.knowledge_query or content
                    ),
                    ToolContext(actor=actor, session=self._session),
                )
                # 有证据时，把检索结果喂给大模型，流式生成规则解答
                if (
                    tool_result.found
                    and tool_result.data is not None
                    and tool_result.data.citations
                ):
                    async for chunk in self._stream_knowledge_reply(
                        model,
                        history_messages,
                        memories,
                        tool_result.data.citations,
                    ):
                        reply_parts.append(chunk)
                        yield ("delta", {"content": chunk})
                    streamed = True
                else:
                    # 无证据时不调用模型，杜绝凭空作答。
                    reply_parts.append(KNOWLEDGE_NOT_FOUND_REPLY)
                trace.record("tool.knowledge", found=tool_result.found)
            # 运单查询：查本人运单，运单号取语义理解结果或正则兜底。
            elif route == "read_tool":
                tool_result = await ShipmentReadTool().execute(
                    ShipmentReadInput(
                        shipment_no=understanding.shipment_no
                        or _extract_shipment_no(content)
                    ),
                    ToolContext(actor=actor, session=self._session),
                )
                async for chunk in self._stream_tool_reply(
                    model, history_messages, memories, tool_result
                ):
                    reply_parts.append(chunk)
                    yield ("delta", {"content": chunk})
                streamed = True
                trace.record("tool.shipment", found=tool_result.found)
            # 地址簿查询：返回本人地址簿，供草稿选址或管理查看。
            elif route == "address_tool":
                tool_result = await AddressBookTool().execute(
                    ToolContext(actor=actor, session=self._session)
                )
                async for chunk in self._stream_tool_reply(
                    model, history_messages, memories, tool_result
                ):
                    reply_parts.append(chunk)
                    yield ("delta", {"content": chunk})
                streamed = True
                trace.record("tool.addresses", found=tool_result.found)
            # 身份查询：返回本人账号信息（不含敏感凭据）。
            elif route == "identity_tool":
                tool_result = await IdentityTool().execute(
                    ToolContext(actor=actor, session=self._session)
                )
                async for chunk in self._stream_tool_reply(
                    model, history_messages, memories, tool_result
                ):
                    reply_parts.append(chunk)
                    yield ("delta", {"content": chunk})
                streamed = True
                trace.record("tool.identity", found=tool_result.found)
            # 运费规则查询：调确定性业务服务，金额不让模型瞎报。
            elif route == "pricing_rule":
                tool_result = await PricingRuleTool().execute(
                    ToolContext(actor=actor, session=self._session)
                )
                async for chunk in self._stream_tool_reply(
                    model, history_messages, memories, tool_result
                ):
                    reply_parts.append(chunk)
                    yield ("delta", {"content": chunk})
                streamed = True
                trace.record("tool.pricing_rule", found=tool_result.found)
            # 草稿填写：跳进 draft agentic loop，模型边调 update_draft 工具
            # 边追问；loop 完成后字段齐全就自动报价并提示确认。
            elif route == "draft":
                # 理解层已结构化提取草稿字段，先确定性落库，避免 draft loop 二次
                # 转述用户原话时把重量/尺寸等字段填错；draft loop 只补漏剩余字段。
                await self._update_draft_from_understanding(
                    conversation.id, actor, understanding, addresses
                )
                draft_holder: dict[str, object] = {}
                async for chunk in self._stream_draft_with_quote(
                    conversation.id,
                    actor,
                    content,
                    history_messages,
                    addresses,
                    model,
                    draft_holder,
                ):
                    reply_parts.append(chunk)
                    yield ("delta", {"content": chunk})
                pending_address = cast(
                    dict[str, object] | None, draft_holder.get("pending_address")
                )
                streamed = True
                trace.record("draft.loop_completed")
            # 确认下单：签发并消费一次性授权，在同一事务创建运单；
            # 失败时把错误信息作为回复返回，不让整轮崩。
            elif route == "confirmation":
                # 草稿尚未报价就绪时，用户多半是「填寄件信息 + 问运费 + 条件式下单」的
                # 复合请求被误判成了敏感动作。若识别结果确实携带寄件信息槽位，
                # 降级回 draft loop 填草稿并自动报价，而不是冷回「先告诉我寄件信息」。
                draft = await DraftService(self._session).get_or_create(
                    conversation.id, actor
                )
                if (
                    draft.status != "READY_FOR_CONFIRMATION"
                    and _has_draft_fields(understanding.draft)
                ):
                    await self._update_draft_from_understanding(
                        conversation.id, actor, understanding, addresses
                    )
                    draft_holder: dict[str, object] = {}
                    async for chunk in self._stream_draft_with_quote(
                        conversation.id,
                        actor,
                        content,
                        history_messages,
                        addresses,
                        model,
                        draft_holder,
                    ):
                        reply_parts.append(chunk)
                        yield ("delta", {"content": chunk})
                    pending_address = cast(
                        dict[str, object] | None, draft_holder.get("pending_address")
                    )
                    streamed = True
                    trace.record("confirmation.degraded_to_draft")
                else:
                    try:
                        reply_parts.append(
                            await self._confirm_shipment(
                                conversation.id, actor, str(trace.trace_id)
                            )
                        )
                    except AppError as error:
                        reply_parts.append(error.message)
                    trace.record("shipment.confirmation_handled")
            # 自由回复-追问：图外 LLM 判定置信度低已生成追问，直接用，不再调模型。
            elif route == "respond" and understanding.clarification_question:
                reply_parts.append(understanding.clarification_question)
                trace.record("understanding.clarification")
            # 自由回复：让模型基于历史 + 记忆自然作答，不调任何业务工具。
            elif route == "respond":
                context = build_model_context(history_messages, memories)
                async for chunk in model.stream(context):
                    if chunk:
                        reply_parts.append(chunk)
                        yield ("delta", {"content": chunk})
                streamed = True
                trace.record("model.stream_completed")
            else:
                # 未接入的工具分支只返回图生成的安全动作，不让模型伪造业务结果。
                reply_parts.append(
                    graph_result.get("response", "请求已进入受控处理流程。")
                )
        except ModelUnavailableError:
            # 流式过程中模型挂掉：用户消息已落库，把会话标为 WAITING_RETRY
            # 让前端可重试；模型故障不能让前端拿到不完整回复当作成功。
            conversation.status = "WAITING_RETRY"
            conversation.updated_at = Clock.now()
            await self._session.commit()
            raise AppError(
                code="AGENT_MODEL_UNAVAILABLE",
                message="AI 服务暂时不可用，会话消息已保存，请稍后重试",
                status_code=503,
            )

        # —— 阶段六：非流式分支兜底 + 空回复保护 ——
        # 走 confirmation/blocked 等非流式分支时，reply_parts 已拼好但还没
        # yield；这里统一补一次 delta。空回复视为故障，不能落一条空助手消息。
        if not streamed:
            yield ("delta", {"content": "".join(reply_parts)})
        reply = "".join(reply_parts)
        if not reply:
            conversation.status = "WAITING_RETRY"
            conversation.updated_at = Clock.now()
            await self._session.commit()
            raise AppError(
                code="AGENT_EMPTY_RESPONSE",
                message="AI 未返回有效内容，请稍后重试",
                status_code=503,
            )

        # —— 阶段七：持久化助手消息，envelope 留下完整审计快照 ——
        # envelope 同时记录图外理解结果（intents/confidence/recognition_path）
        # 与图内裁决结果（intent/risk/route/next_action），便于事后追溯任意一通
        # 会话经过的语义判断和路由路径。
        assistant_message = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            envelope={
                # 本轮追踪 id，关联 AgentTrace 全部事件，便于跨日志串联。
                "trace_id": str(trace.trace_id),
                # 图内裁决后的最终意图（路由依据）。
                "intent": graph_result.get("intent"),
                # 图外 LLM 理解的候选意图（最多 3 个，按置信度排序）。
                "intents": understanding.intents,
                # 图外语义置信度，低于阈值会走追问分支。
                "confidence": understanding.confidence,
                # 识别路径（LLM/RULE/...），区分模型判定与确定性规则改写。
                "recognition_path": understanding.recognition_path,
                # 图内裁决的风险等级（LOW/PERSONAL_DATA/WRITE_ACTION/BLOCKED）。
                "risk": graph_result.get("risk"),
                # 图内最终路由，与下方分发分支一一对应。
                "route": route,
                # 图产出的确定性动作标记（如 QUERY_PRICING_RULES），不含业务结果。
                "next_action": graph_result.get("next_action"),
                # 工具返回的结构化结果；无工具调用时为 None。
                "tool_result": tool_result.model_dump(mode="json")
                if tool_result is not None
                else None,
                # 草稿 loop 留下的待保存地址信号，供下一轮 _maybe_save_address 消费。
                "pending_address": pending_address,
                # AgentTrace 的摘要事件序列，记录本轮各阶段时序。
                "trace": trace.summary(),
            },
            created_at=Clock.now(),
        )
        self._session.add(assistant_message)
        conversation.status = "ACTIVE"
        conversation.updated_at = assistant_message.created_at
        await self._session.commit()
        yield (
            "done",
            MessageView.model_validate(assistant_message).model_dump(mode="json"),
        )

    async def _stream_tool_reply(
        self,
        model: ModelAdapter,
        history: list[ModelMessage],
        memories: list[str],
        tool_result: ToolResult[BaseModel],
    ) -> AsyncIterator[str]:
        """把工具结果回喂模型，流式生成自然语言回复。"""
        context = build_model_context(history, memories, [tool_result.model_dump_json()])
        async for chunk in model.stream(context):
            if chunk:
                yield chunk

    async def _stream_knowledge_reply(
        self,
        model: ModelAdapter,
        history: list[ModelMessage],
        memories: list[str],
        citations: list[KnowledgeCitation],
    ) -> AsyncIterator[str]:
        """把检索证据结构化为证据块，配合专用指令流式生成规则解答。

        与普通闲聊不同，知识解答必须严格依据证据。这里不沿用 build_model_context
        （那会把解答指令 append 在历史之后），而是把解答指令与证据作为紧随身份指令的
        最高优先级 system 消息，避免模型被「寄件助手」闲聊身份和长历史带偏而答非所问。
        """
        evidence = _format_knowledge_evidence(citations)
        messages = [
            ModelMessage(role="system", content=SYSTEM_PROMPT.strip()),
            ModelMessage(
                role="system",
                content=redact_text(
                    KNOWLEDGE_ANSWER_PROMPT + "\n\n【知识证据】\n" + evidence
                ),
            ),
        ]
        if memories:
            messages.append(
                ModelMessage(
                    role="system",
                    content=redact_text("用户偏好：" + "；".join(memories[:10])),
                )
            )
        # 只回放最近一轮上下文（当前问题 + 上一条），避免长历史寄件闲聊稀释知识解答。
        for message in history[-2:]:
            messages.append(
                ModelMessage(role=message.role, content=redact_text(message.content))
            )
        async for chunk in model.stream(messages):
            if chunk:
                yield chunk

    async def stream_message(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        model: ModelAdapter,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """流式单轮：转发共享编排事件，错误折叠为 SSE error 事件。"""
        await self.get_owned(conversation_id, actor)
        try:
            async for event, payload in self._run_turn(
                conversation_id, actor, content, model
            ):
                yield (event, payload)
        except AppError as error:
            yield ("error", {"code": error.code, "message": error.message})

    @staticmethod
    def _initial_graph_state(
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        history: list[AgentMessage],
        understanding: UnderstandingResult,
    ) -> AgentState:
        """从可信身份和持久化历史构造有界图状态。"""
        return {
            # ① 可信身份（来自认证 actor，不是从消息里提取）
            "conversation_id": str(conversation_id),
            "user_id": str(actor.id),
            "user_role": actor.role.value,
            "user_message": content,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
            # ② 语义理解结果（图外用 LLM 算好，全部加 semantic_ 前缀）
            "semantic_intents": understanding.intents,
            "semantic_intent": understanding.primary_intent,
            "semantic_confidence": understanding.confidence,
            "semantic_shipment_no": understanding.shipment_no,
            "semantic_knowledge_query": understanding.knowledge_query,
            "semantic_draft": understanding.draft.model_dump(exclude_none=True),
            "requires_confirmation": understanding.requires_confirmation,
            "clarification_question": understanding.clarification_question,
            
            # ③ 执行预算（图内每个节点都会读这几个字段做守门）
            "turn_count": 0,
            "tool_call_count": 0,
            "max_turns": 8,
            "max_tool_calls": 4,
            "execution_started_at": monotonic(),
            "timeout_seconds": 30.0,
        }

    async def _understand(
        self,
        model: ModelAdapter,
        history: list[AgentMessage],
        content: str,
        actor: CurrentUser,
    ) -> tuple[UnderstandingResult, list[Address]]:
        """加载最小地址标签并执行结构化理解，不向模型暴露电话和门牌。"""
        addresses = await list_addresses(self._session, actor)
        result = await UnderstandingService(model).understand(
            [ModelMessage(role=item.role, content=item.content) for item in history],
            content,
            [address.label for address in addresses if address.label],
        )
        return result, addresses

    async def _stream_draft_loop(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        history: list[ModelMessage],
        addresses: list[Address],
        model: ModelAdapter,
        result_holder: dict[str, object],
    ) -> AsyncIterator[str]:
        """流式草稿填写 loop：内容增量即时 yield，pending_address 存入 result_holder。

        通过 asyncio.Queue 在 LangGraph 节点执行期间并发传递 token 增量，
        让用户在 agentic loop 的最终模型调用阶段看到逐字输出。
        """
        # 加载/创建草稿，获取当前已填字段和缺失字段
        draft = await DraftService(self._session).get_or_create(conversation_id, actor)
        summary = await DraftService(self._session).describe(draft, actor)
        filled_fields = (
            "；".join(f"{item['label']}：{item['value']}" for item in summary)
            if summary
            else "（无）"
        )
        thread_id = str(conversation_id)
        checkpointer = self._checkpointer
        if checkpointer is None:
            checkpointer = await get_shared_checkpointer()
        
        # 清理上一轮的checkpoint，避免读到残留历史
        await _clear_thread(checkpointer, thread_id)
        
        # 构建草稿 loop 的初始 state
        loop_state: AgentState = {
            "conversation_id": str(conversation_id),
            "user_id": str(actor.id),
            "user_message": content,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
            "draft_missing_fields": draft.missing_fields,
            "draft_filled_fields": filled_fields,
            "address_labels": [address.label for address in addresses if address.label],
            "turn_count": 0,
            "tool_call_count": 0,
            "max_turns": 8,
            "max_tool_calls": 4,
            "execution_started_at": monotonic(),
            "timeout_seconds": 30.0,
        }
        # queue 协议：模型 token 增量是 str，结束哨兵是 None。
        # 哨兵必须由 _run_graph 的 finally 投递，保证图异常时消费端也能退出。
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        
        # 当场构建草稿子图
        graph = build_draft_loop_graph(
            model,
            actor=actor,
            session=self._session,
            addresses=addresses,
            checkpointer=checkpointer,
            stream_queue=queue,
        )

        async def _run_graph() -> dict[str, Any]:
            try:
                return await graph.ainvoke(
                    loop_state,
                    config={"configurable": {"thread_id": thread_id}},
                )
            finally:
                # 即使图抛异常也要投递哨兵，否则外层 while 会永久阻塞。
                await queue.put(None)

        # 异步运行子图，通过 queue 流式产出 token
        graph_task = asyncio.create_task(_run_graph())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        graph_result = await graph_task
        result_holder["pending_address"] = graph_result.get("pending_address")

    async def _stream_draft_with_quote(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        history_messages: list[ModelMessage],
        addresses: list[Address],
        model: ModelAdapter,
        result_holder: dict[str, object],
    ) -> AsyncIterator[str]:
        """跑草稿 loop 并在字段齐全后追加自动报价，供 draft 与 confirmation 降级共用。"""
        async for chunk in self._stream_draft_loop(
            conversation_id, actor, content, history_messages, addresses, model, result_holder
        ):
            yield chunk
        quote_reply = await self._auto_quote_if_complete(conversation_id, actor)
        if quote_reply:
            yield quote_reply

    async def _auto_quote_if_complete(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> str | None:
        """草稿字段齐全时自动生成报价并提示确认，报价失败降级提示而不整轮失败。"""
        draft = await DraftService(self._session).get_or_create(conversation_id, actor)
        if draft.missing_fields:
            return None
        try:
            validation = await DraftService(self._session).validate_and_quote(
                conversation_id, actor
            )
        except AppError:
            return "报价暂时算不出来，稍后再试一下哦。"
        total = validation.quote.total_cents / 100
        return f"寄件信息都齐啦，本次运费预计 {total:.2f} 元，回复「确认」就可以下单了～"

    async def _confirm_shipment(
        self, conversation_id: UUID, actor: CurrentUser, trace_id: str
    ) -> str:
        """用户整句确认后，签发并消费一次性授权，在同一事务创建运单。"""
        draft = await DraftService(self._session).get_or_create(conversation_id, actor)
        if draft.status != "READY_FOR_CONFIRMATION":
            return "还没有可确认的报价哦，先告诉我寄件信息，我来帮你补齐～"
        # 先签发一次性授权，再由 create_shipment 消费它；授权只能用一次，
        # 防止用户多次"确认"重复下单或并发下单造成幂等性问题。
        grant = await GrantService(self._session).issue(conversation_id, actor)
        shipment = await AgentWriteService(self._session).create_shipment(
            grant.id, actor, trace_id
        )
        quote = await self._session.get(QuoteSnapshot, grant.quote_id)
        if quote is None:
            raise AppError("AGENT_QUOTE_MISSING", "报价快照不存在", 409)
        pending_save = await self._ephemeral_address_ids(draft)
        # 下单后草稿已消费，重置状态防止重复下单，也避免前端继续展示确认按钮。
        draft.status = "SHIPMENT_CREATED"
        if pending_save:
            draft.payload = {**draft.payload, "pending_save_address_ids": pending_save}
        reply = (
            f"太好啦，运单已经创建好咯！运单号 {shipment.shipment_no}，"
            f"待支付 {quote.total_cents / 100:.2f} 元，前往运单详情完成支付就可以啦。"
        )
        if pending_save:
            reply += "对了，这次寄件用了一个新地址，要不要帮你也存进地址簿？以后寄件直接选就行，回复「保存」就可以啦。"
        return reply

    async def record_consumption_receipt(
        self,
        grant_id: UUID,
        actor: CurrentUser,
        shipment: ShipmentView,
    ) -> None:
        """确认下单成功后，把下单回执作为助手消息写入会话历史。

        前端「确认下单」按钮走独立的 issue/consume 授权接口，不经过对话流，
        下单成功不会产生 assistant 消息；这里补写一条回执，让用户回到聊天
        记录也能看到下单结果，而不是只剩报价气泡。同时补写一条用户「确认」
        消息，模拟用户在按钮确认时已经打出确认词，使按钮路径与对话确认路径
        的历史记录保持一致。
        """
        grant = await self._session.get(AgentActionGrant, grant_id)
        # 归属校验：授权必须属于当前用户，防止跨用户写入回执消息。
        if grant is None or grant.owner_id != actor.id:
            return
        quote = await self._session.get(QuoteSnapshot, grant.quote_id)
        if quote is None:
            return
        reply = (
            f"太好啦，运单已经创建好咯！运单号 {shipment.shipment_no}，"
            f"待支付 {quote.total_cents / 100:.2f} 元，前往运单详情完成支付就可以啦。"
        )
        now = Clock.now()
        self._session.add(
            AgentMessage(
                conversation_id=grant.conversation_id,
                role="user",
                content="确认",
                envelope=None,
                created_at=now,
            )
        )
        self._session.add(
            AgentMessage(
                conversation_id=grant.conversation_id,
                role="assistant",
                content=reply,
                envelope={"action": "SHIPMENT_CREATED", "grant_id": str(grant_id)},
                created_at=now + timedelta(milliseconds=1),
            )
        )

    async def _ephemeral_address_ids(self, draft: AgentShipmentDraft) -> list[str]:
        """收集草稿里不在地址簿的临时地址 id，供寄件后询问是否保存。"""
        ids: list[str] = []
        for key in ("sender_address_id", "receiver_address_id"):
            value = draft.payload.get(key)
            if value is None:
                continue
            try:
                address = await self._session.get(Address, UUID(str(value)))
            except (ValueError, TypeError):
                continue
            if (
                address is not None
                and address.owner_id == draft.owner_id
                and address.ephemeral
            ):
                ids.append(str(address.id))
        return ids

    async def _maybe_save_address(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        understanding: UnderstandingResult,
    ) -> UnderstandingResult:
        """下单后待保存临时地址且整句为保存确认时，确定性转为正式地址。"""
        if not is_save_address_word(content):
            return understanding
        draft = await self._session.scalar(
            select(AgentShipmentDraft).where(
                AgentShipmentDraft.conversation_id == conversation_id,
                AgentShipmentDraft.owner_id == actor.id,
            )
        )
        if draft is None:
            return understanding
        pending = cast(
            list[str], draft.payload.get("pending_save_address_ids") or []
        )
        if not pending:
            return understanding
        for value in pending:
            try:
                address = await self._session.get(Address, UUID(str(value)))
            except (ValueError, TypeError):
                continue
            if address is not None and address.owner_id == actor.id:
                address.ephemeral = False
        draft.payload = {**draft.payload, "pending_save_address_ids": []}
        return understanding.model_copy(
            update={
                "intents": ["GENERAL_CHAT"],
                "primary_intent": "GENERAL_CHAT",
                "confidence": 1.0,
                "recognition_path": "RULE",
                "clarification_question": "已保存到地址簿啦，下次寄件直接选就行～",
            }
        )

    async def _maybe_confirm(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        understanding: UnderstandingResult,
    ) -> UnderstandingResult:
        """草稿已报价待确认且整句为确认词时，确定性改写为 SENSITIVE_ACTION。"""
        # 只有闲聊或已是敏感动作的意图才能被"确认"改写；其他业务意图
        # （如查询、知识检索）不应被一句"确认"误判成下单。
        if understanding.primary_intent not in ("GENERAL_CHAT", "SENSITIVE_ACTION"):
            return understanding
        if not is_confirmation_word(content):
            return understanding
        draft = await self._session.scalar(
            select(AgentShipmentDraft).where(
                AgentShipmentDraft.conversation_id == conversation_id,
                AgentShipmentDraft.owner_id == actor.id,
            )
        )
        if draft is None or draft.status != "READY_FOR_CONFIRMATION":
            return understanding
        return understanding.model_copy(
            update={
                "intents": ["SENSITIVE_ACTION"],
                "primary_intent": "SENSITIVE_ACTION",
                "confidence": 1.0,
                "requires_confirmation": True,
                "recognition_path": "RULE",
            }
        )

    async def save_draft_address(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        payload: DraftAddressCreate,
    ) -> DraftView:
        """创建草稿用收寄地址（保存或临时），并回填草稿地址与区县代码。

        命中既有相同地址时复用，避免地址簿反复弹表单累积重复条目。
        """
        await self.get_owned(conversation_id, actor)
        existing = await find_matching_address(
            self._session,
            actor.id,
            payload.recipient_name,
            payload.phone,
            payload.district_region_id,
            payload.detail,
        )
        if existing is not None:
            if payload.save:
                if existing.ephemeral:
                    existing.ephemeral = False
                    existing.label = existing.label or payload.label
                elif existing.label is None and payload.label is not None:
                    existing.label = payload.label
            address = existing
        else:
            address = Address(
                owner_id=actor.id,
                label=payload.label if payload.save else None,
                recipient_name=payload.recipient_name,
                phone=payload.phone,
                detail=payload.detail,
                ephemeral=not payload.save,
            )
            await assign_region_path(
                self._session,
                address,
                payload.province_region_id,
                payload.city_region_id,
                payload.district_region_id,
            )
            self._session.add(address)
            await self._session.flush()
        patch = DraftPatch(
            sender_address_id=address.id if payload.role == "sender" else None,
            receiver_address_id=address.id if payload.role == "receiver" else None,
            origin_district_code=(
                address.district_code if payload.role == "sender" else None
            ),
            destination_district_code=(
                address.district_code if payload.role == "receiver" else None
            ),
        )
        draft = await DraftService(self._session).update(conversation_id, actor, patch)
        return draft

    async def _update_draft_from_understanding(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        understanding: UnderstandingResult,
        addresses: list[Address],
    ) -> str:
        """把模型候选字段解析为本人资源，再交给确定性草稿服务持久化。"""
        candidate = understanding.draft
        patch_data = candidate.model_dump(
            exclude={"sender_address_label", "receiver_address_label"},
            exclude_none=True,
        )
        unresolved: list[str] = []
        sender = _match_address(candidate.sender_address_label, addresses)
        receiver = _match_address(candidate.receiver_address_label, addresses)
        if candidate.sender_address_label:
            if sender is None:
                unresolved.append(f"寄件地址“{candidate.sender_address_label}”")
            else:
                patch_data["sender_address_id"] = sender.id
                patch_data["origin_district_code"] = sender.district_code
        if candidate.receiver_address_label:
            if receiver is None:
                unresolved.append(f"收件地址“{candidate.receiver_address_label}”")
            else:
                patch_data["receiver_address_id"] = receiver.id
                patch_data["destination_district_code"] = receiver.district_code
        for source, target in (
            ("actual_weight_grams", "estimated_weight_grams"),
            ("length_cm", "estimated_length_cm"),
            ("width_cm", "estimated_width_cm"),
            ("height_cm", "estimated_height_cm"),
        ):
            if source in patch_data:
                patch_data[target] = patch_data.pop(source)
        if patch_data:
            draft = await DraftService(self._session).update(
                conversation_id, actor, DraftPatch.model_validate(patch_data)
            )
            await self._session.commit()
        else:
            draft = DraftView.model_validate(
                await DraftService(self._session).get_or_create(
                    conversation_id, actor
                )
            )
        if unresolved:
            return "我没有在你的地址簿中唯一找到" + "、".join(unresolved) + "。请直接告诉我地址标签，或先到地址簿新增地址。"
        if understanding.clarification_question:
            return understanding.clarification_question
        missing = "、".join(draft.missing_fields)
        return (
            f"寄件信息已经更新。还需要补充：{missing}。"
            if missing
            else "寄件信息已经齐全，可以生成报价了。"
        )

    async def _load_messages(self, conversation_id: UUID) -> list[AgentMessage]:
        statement = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def delete_conversation(self, conversation_id: UUID, actor: CurrentUser, request_id: str) -> None:
        """删除会话正文和关联草稿/授权，保留不含正文的匿名审计记录。"""
        conversation = await self.get_owned(conversation_id, actor)
        await AuditService(self._session).record(
            actor=str(actor.id), action="agent.conversation.deleted",
            resource="agent-conversation:anonymous", before_summary={"conversation_id": str(conversation.id)},
            after_summary={"deleted": True}, reason="user_requested", request_id=request_id,
        )
        await self._session.delete(conversation)
        await self._session.flush()

    async def _load_memories(
        self, owner_id: UUID, query: str | None = None
    ) -> list[str]:
        """语义召回长期记忆：query 为当前用户消息，嵌入失败回退 recency。"""
        return await MemoryService(self._session).recall(owner_id, query)


def _has_draft_fields(draft: DraftCandidate) -> bool:
    """识别结果是否携带任何草稿槽位，用于 confirmation 降级判断。"""
    return bool(draft.model_dump(exclude_none=True))


def _extract_shipment_no(content: str) -> str | None:
    """仅提取显式 YT 运单号；未提供时由服务返回最近一票本人运单。"""
    import re

    match = re.search(r"\bYT[A-Z0-9]{4,32}\b", content.upper())
    return match.group(0) if match else None


def _match_address(label: str | None, addresses: list[Address]) -> Address | None:
    """只接受当前用户地址簿中的唯一标签，避免模糊匹配选错收寄地址。"""
    if not label:
        return None
    matches = [address for address in addresses if address.label == label]
    return matches[0] if len(matches) == 1 else None


def _conversation_title(content: str) -> str:
    """使用首条用户消息生成稳定、紧凑的会话标题。"""
    normalized = " ".join(content.split())
    return normalized[:30]


def _format_knowledge_evidence(citations: list[KnowledgeCitation]) -> str:
    """把检索证据拼成结构化文本块，只保留回答所需字段，不夹带工具元数据。"""
    blocks: list[str] = []
    for index, citation in enumerate(citations, start=1):
        location_parts = list(citation.section_path)
        if citation.page_start is not None:
            if citation.page_end is not None and citation.page_end != citation.page_start:
                location_parts.append(f"第{citation.page_start}-{citation.page_end}页")
            else:
                location_parts.append(f"第{citation.page_start}页")
        location = "/".join(part for part in location_parts if part)
        header = f"【证据 {index}】《{citation.filename}》"
        if citation.title:
            header += f" {citation.title}"
        if location:
            header += f"（{location}）"
        blocks.append(f"{header}\n{citation.content}")
    return "\n\n".join(blocks)
