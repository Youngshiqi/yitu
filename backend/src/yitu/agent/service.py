"""Agent 会话持久化和模型调用服务。"""

import inspect
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import assign_region_path, list_addresses
from yitu.agent.context import build_model_context
from yitu.agent.draft_loop import build_draft_loop_graph
from yitu.agent.drafts import DraftPatch, DraftService, DraftView
from yitu.agent.graph import build_agent_graph
from yitu.agent.model_adapter import ModelAdapter, ModelMessage, ModelUnavailableError
from yitu.agent.models import AgentConversation, AgentMemory, AgentMessage
from yitu.agent.nodes import security_refusal
from yitu.agent.privacy import redact_text
from yitu.agent.prompts import (
    BUDGET_REFUSAL,
    KNOWLEDGE_ANSWER_PROMPT,
    KNOWLEDGE_NOT_FOUND_REPLY,
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
from yitu.agent.tools.shipments import ShipmentReadInput, ShipmentReadTool
from yitu.agent.tracing import AgentTrace
from yitu.agent.understanding import (
    DraftCandidate,
    UnderstandingResult,
    UnderstandingService,
    preprocess_text,
)
from yitu.identity.service import CurrentUser
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError

_default_checkpointer = MemorySaver()  # 进程级单例，跨请求共享草稿 loop 的 thread 状态


def get_default_checkpointer() -> Any:
    """返回进程级单例 checkpointer，供 API 层依赖注入复用。"""
    return _default_checkpointer


async def _clear_thread(checkpointer: Any, thread_id: str) -> None:
    """清空指定 thread 的 checkpoint，让每轮草稿 loop 从干净状态开始。

    当前 MemorySaver.delete_thread 为同步，未来 PostgresSaver 可能为异步，
    这里对 awaitable 结果统一 await，保证两种实现都能复用。
    """
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
        self._checkpointer = (
            checkpointer if checkpointer is not None else _default_checkpointer
        )

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
        return list((await self._session.scalars(statement)).all())

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

        history = await self._load_messages(conversation.id)
        memories = await self._load_memories(actor.id)
        refusal = security_refusal(preprocess_text(content).normalized)
        if refusal is not None:
            understanding = UnderstandingResult(
                intents=[refusal[0]],
                primary_intent=refusal[0],
                confidence=1.0,
                draft=DraftCandidate(),
            )
            addresses: list[Address] = []
        else:
            try:
                understanding, addresses = await self._understand(
                    model, history, content, actor
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

        route = graph_result.get("route")
        tool_result: ToolResult[BaseModel] | None = None
        pending_address: dict[str, object] | None = None
        history_messages = [
            ModelMessage(role=item.role, content=item.content) for item in history
        ]
        reply_parts: list[str] = []
        try:
            if route == "knowledge":
                tool_result = await KnowledgeSearchTool().execute(
                    KnowledgeSearchInput(
                        query=understanding.knowledge_query or content
                    ),
                    ToolContext(actor=actor, session=self._session),
                )
                if (
                    tool_result.found
                    and tool_result.data is not None
                    and tool_result.data.citations
                ):
                    reply_parts.append(
                        await self._knowledge_reply(
                            model,
                            history_messages,
                            memories,
                            tool_result.data.citations,
                        )
                    )
                else:
                    # 无证据时不调用模型，杜绝凭空作答。
                    reply_parts.append(KNOWLEDGE_NOT_FOUND_REPLY)
                trace.record("tool.knowledge", found=tool_result.found)
            elif route == "read_tool":
                tool_result = await ShipmentReadTool().execute(
                    ShipmentReadInput(
                        shipment_no=understanding.shipment_no
                        or _extract_shipment_no(content)
                    ),
                    ToolContext(actor=actor, session=self._session),
                )
                reply_parts.append(
                    await self._tool_reply(
                        model, history_messages, memories, tool_result
                    )
                )
                trace.record("tool.shipment", found=tool_result.found)
            elif route == "address_tool":
                tool_result = await AddressBookTool().execute(
                    ToolContext(actor=actor, session=self._session)
                )
                reply_parts.append(
                    await self._tool_reply(
                        model, history_messages, memories, tool_result
                    )
                )
                trace.record("tool.addresses", found=tool_result.found)
            elif route == "identity_tool":
                tool_result = await IdentityTool().execute(
                    ToolContext(actor=actor, session=self._session)
                )
                reply_parts.append(
                    await self._tool_reply(
                        model, history_messages, memories, tool_result
                    )
                )
                trace.record("tool.identity", found=tool_result.found)
            elif route == "draft":
                draft_reply, pending_address = await self._run_draft_loop(
                    conversation.id,
                    actor,
                    content,
                    history_messages,
                    addresses,
                    model,
                )
                reply_parts.append(draft_reply)
                trace.record("draft.loop_completed")
            elif route == "respond" and understanding.clarification_question:
                reply_parts.append(understanding.clarification_question)
                trace.record("understanding.clarification")
            elif route == "respond":
                context = build_model_context(history_messages, memories)
                async for chunk in model.stream(context):
                    if chunk:
                        reply_parts.append(chunk)
                        yield ("delta", {"content": chunk})
                trace.record("model.stream_completed")
            else:
                # 未接入的工具分支只返回图生成的安全动作，不让模型伪造业务结果。
                reply_parts.append(
                    graph_result.get("response", "请求已进入受控处理流程。")
                )
        except ModelUnavailableError:
            conversation.status = "WAITING_RETRY"
            conversation.updated_at = Clock.now()
            await self._session.commit()
            raise AppError(
                code="AGENT_MODEL_UNAVAILABLE",
                message="AI 服务暂时不可用，会话消息已保存，请稍后重试",
                status_code=503,
            )

        if route != "respond":
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

        assistant_message = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            envelope={
                "trace_id": str(trace.trace_id),
                "intent": graph_result.get("intent"),
                "intents": understanding.intents,
                "confidence": understanding.confidence,
                "recognition_path": understanding.recognition_path,
                "risk": graph_result.get("risk"),
                "route": route,
                "next_action": graph_result.get("next_action"),
                "tool_result": tool_result.model_dump(mode="json")
                if tool_result is not None
                else None,
                "pending_address": pending_address,
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

    async def _tool_reply(
        self,
        model: ModelAdapter,
        history: list[ModelMessage],
        memories: list[str],
        tool_result: ToolResult[BaseModel],
    ) -> str:
        """把工具结果回喂模型，生成自然语言回复。"""
        return await model.complete(
            build_model_context(history, memories, [tool_result.model_dump_json()])
        )

    async def _knowledge_reply(
        self,
        model: ModelAdapter,
        history: list[ModelMessage],
        memories: list[str],
        citations: list[KnowledgeCitation],
    ) -> str:
        """把检索证据结构化为证据块，配合专用指令生成规则解答。"""
        evidence = _format_knowledge_evidence(citations)
        messages = build_model_context(history, memories)
        messages.append(
            ModelMessage(
                role="system",
                content=redact_text(
                    KNOWLEDGE_ANSWER_PROMPT + "\n\n【知识证据】\n" + evidence
                ),
            )
        )
        return await model.complete(messages)

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
            "conversation_id": str(conversation_id),
            "user_id": str(actor.id),
            "user_role": actor.role.value,
            "user_message": content,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
            "semantic_intents": understanding.intents,
            "semantic_intent": understanding.primary_intent,
            "semantic_confidence": understanding.confidence,
            "semantic_shipment_no": understanding.shipment_no,
            "semantic_knowledge_query": understanding.knowledge_query,
            "semantic_draft": understanding.draft.model_dump(exclude_none=True),
            "requires_confirmation": understanding.requires_confirmation,
            "clarification_question": understanding.clarification_question,
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

    async def _run_draft_loop(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        content: str,
        history: list[ModelMessage],
        addresses: list[Address],
        model: ModelAdapter,
    ) -> tuple[str, dict[str, object] | None]:
        """把草稿填写交给 agentic loop：模型通过 update_draft 增量填字段。

        返回 (回复文本, 地址簿外新地址的收集信号)；无新地址时信号为 None。
        """
        draft = await DraftService(self._session).get_or_create(conversation_id, actor)
        thread_id = str(conversation_id)
        # 草稿 loop 内部的 assistant/tool 往返只服务于单轮；跨请求上下文由 DB 的
        # history 与草稿 payload 承担。每轮先清空该 thread 的 checkpoint，避免上一轮
        # 的 draft_turns 经 add reducer 累积进本轮、覆盖掉新的 user_message。
        await _clear_thread(self._checkpointer, thread_id)
        loop_state: AgentState = {
            "conversation_id": str(conversation_id),
            "user_id": str(actor.id),
            "user_message": content,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
            "draft_missing_fields": draft.missing_fields,
            "address_labels": [address.label for address in addresses if address.label],
            "turn_count": 0,
            "tool_call_count": 0,
            "max_turns": 8,
            "max_tool_calls": 4,
            "execution_started_at": monotonic(),
            "timeout_seconds": 30.0,
        }
        result = await build_draft_loop_graph(
            model,
            actor=actor,
            session=self._session,
            addresses=addresses,
            checkpointer=self._checkpointer,
        ).ainvoke(
            loop_state,
            config={"configurable": {"thread_id": thread_id}},
        )
        return (
            result.get("draft_response") or BUDGET_REFUSAL,
            result.get("pending_address"),
        )

    async def save_draft_address(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        payload: DraftAddressCreate,
    ) -> DraftView:
        """创建草稿用收寄地址（保存或临时），并回填草稿地址与区县代码。"""
        await self.get_owned(conversation_id, actor)
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

    async def _load_memories(self, owner_id: UUID) -> list[str]:
        rows = await self._session.scalars(
            select(AgentMemory).where(AgentMemory.owner_id == owner_id, AgentMemory.active.is_(True))
        )
        now = Clock.now()
        return [row.content for row in rows.all() if row.expires_at is None or row.expires_at > now]


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
