"""统一执行、流式输出和人工确认恢复的 LangGraph Runner。"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langgraph.types import Command

from yitu.agent.runtime.event_mapper import (
    AgentEventMapper,
    AssistantMessageStored,
    PublicAgentEvent,
    TokenGenerated,
    UserMessageStored,
    WorkflowFailed,
)
from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.schemas import AgentTurnView, MessageView

_CONFIRM_WORDS = {"确认", "确认寄件", "确认下单", "同意", "confirm"}
_CANCEL_WORDS = {"取消", "取消寄件", "不要了", "cancel"}


class AgentGraphRunner:
    """驱动已编译图，并把执行事件映射到稳定的 API 契约。"""

    def __init__(self, graph: Any, mapper: AgentEventMapper | None = None) -> None:
        self._graph = graph
        self._mapper = mapper or AgentEventMapper()

    async def invoke_message(
        self,
        conversation_id: UUID,
        content: str,
        context: AgentRuntimeContext,
    ) -> AgentTurnView:
        user_message: MessageView | None = None
        assistant_message: MessageView | None = None
        async for event, payload in self.stream_message(
            conversation_id, content, context
        ):
            if event == "user_message":
                user_message = MessageView.model_validate(payload)
            elif event == "done":
                assistant_message = MessageView.model_validate(payload)
        if user_message is None or assistant_message is None:
            raise RuntimeError("Agent 未产生完整往返结果")
        return AgentTurnView(
            user_message=user_message,
            assistant_message=assistant_message,
        )

    async def stream_message(
        self,
        conversation_id: UUID,
        content: str,
        context: AgentRuntimeContext,
    ) -> AsyncIterator[PublicAgentEvent]:
        # conversation_id 同时作为业务会话 ID 和 LangGraph thread_id，
        # 用于在不同请求之间恢复同一会话的 State/interrupt。
        config: dict[str, Any] = {"configurable": {"thread_id": str(conversation_id)}}
        try:
            # 先检查是否停在人工确认节点；只有固定确认词/取消词才恢复 interrupt。
            pending = await self._pending_interrupt(config)
            normalized = _normalize_decision(content)
            user_payload = await context.conversation_service.append_message(
                conversation_id,
                context.actor_id,
                role="user",
                content=content,
            )
            mapped = self._mapper.map(UserMessageStored(payload=user_payload))
            if mapped is not None:
                yield mapped

            if pending and normalized in {"confirm", "cancel"}:
                graph_input: Any = Command(resume={"decision": normalized})
            elif pending:
                # 用户发送了与确认无关的新问题：先结束旧的确认等待，再以普通新回合处理。
                await self._drain(
                    Command(resume={"decision": "defer"}), config, context
                )
                graph_input = {
                    "conversation_id": str(conversation_id),
                    "user_message": content,
                }
            else:
                graph_input = {
                    "conversation_id": str(conversation_id),
                    "user_message": content,
                }

            # custom 流承载节点产生的 token，values 流保留最终 State，便于识别 interrupt。
            final_state: dict[str, object] = {}
            async for mode, chunk in self._graph.astream(
                graph_input,
                config,
                context=context,
                stream_mode=["custom", "values"],
            ):
                if mode == "custom" and isinstance(chunk, dict):
                    token = (
                        chunk.get("content") if chunk.get("type") == "token" else None
                    )
                    if isinstance(token, str) and token:
                        event = self._mapper.map(TokenGenerated(content=token))
                        if event is not None:
                            yield event
                elif mode == "values" and isinstance(chunk, dict):
                    final_state = chunk

            # interrupt 不会产生普通 assistant 消息，因此由 Runner 根据确认负载生成确认卡片；
            # 其他路径的 assistant 消息已经由 finalize/handle_failure 节点持久化。
            interrupt_payload = _interrupt_payload(final_state)
            assistant_payload: dict[str, object] | None
            if interrupt_payload is not None:
                assistant_payload = await self._store_confirmation(
                    conversation_id, context, interrupt_payload
                )
            else:
                history = await context.conversation_service.load_history(
                    conversation_id, context.actor_id, limit=1
                )
                assistant_payload = history[-1] if history else None
            if isinstance(assistant_payload, dict):
                event = self._mapper.map(
                    AssistantMessageStored(payload=assistant_payload)
                )
                if event is not None:
                    yield event
        except Exception:  # noqa: BLE001 - Runtime 统一稳定公开错误，内部异常留给日志追踪
            event = self._mapper.map(
                WorkflowFailed(
                    code="AGENT_RUNTIME_ERROR",
                    message="AI 助手暂时无法完成请求，请稍后重试",
                )
            )
            if event is not None:
                yield event

    async def _pending_interrupt(self, config: dict[str, Any]) -> bool:
        snapshot = await self._graph.aget_state(config)
        return bool(getattr(snapshot, "interrupts", ()))

    async def _drain(
        self,
        command: Command[Any],
        config: dict[str, Any],
        context: AgentRuntimeContext,
    ) -> None:
        async for _ in self._graph.astream(command, config, context=context):
            pass

    async def _store_confirmation(
        self,
        conversation_id: UUID,
        context: AgentRuntimeContext,
        payload: dict[str, object],
    ) -> dict[str, object]:
        total = payload.get("total_cents", 0)
        amount = int(total) / 100 if isinstance(total, int) else 0
        summary = str(payload.get("summary", ""))
        content = f"寄件信息：{summary}。报价 {amount:.2f} 元，请确认是否创建运单。"
        return await context.conversation_service.append_message(
            conversation_id,
            context.actor_id,
            role="assistant",
            content=content,
            envelope={"confirmation": payload},
        )


def _normalize_decision(content: str) -> str | None:
    normalized = "".join(content.strip().lower().split())
    if normalized in _CONFIRM_WORDS:
        return "confirm"
    if normalized in _CANCEL_WORDS:
        return "cancel"
    return None


def _interrupt_payload(state: dict[str, object]) -> dict[str, object] | None:
    raw = state.get("__interrupt__")
    if not isinstance(raw, tuple | list) or not raw:
        return None
    value = getattr(raw[0], "value", None)
    return value if isinstance(value, dict) else None
