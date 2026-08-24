"""Agent 图测试使用的行为型内存端口。"""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from yitu.agent.model_adapter import (
    ModelMessage,
    ToolCallResult,
    ToolStreamEvent,
)
from yitu.agent.workflow_state.contracts import (
    AssistantToolCall,
    AssistantToolObservation,
    ConfirmationSnapshot,
    DraftProgress,
    DraftToolCall,
    KnowledgeEvidence,
    KnowledgeSearchInput,
    QuoteProgress,
    ShipmentReceipt,
)


class ScriptedModelPort:
    def __init__(self, responses: Sequence[ToolCallResult]) -> None:
        self._responses = list(responses)
        self.requests: list[list[ModelMessage]] = []

    async def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]:
        del tools
        self.requests.append(list(messages))
        response = self._responses.pop(0)
        if response.content:
            yield ToolStreamEvent(delta=response.content)
        yield ToolStreamEvent(result=response)


class FakeKnowledgePort:
    def __init__(self, evidence: KnowledgeEvidence) -> None:
        self.evidence = evidence
        self.queries: list[KnowledgeSearchInput] = []

    async def search(
        self,
        request: KnowledgeSearchInput,
        *,
        actor_id: UUID,
    ) -> KnowledgeEvidence:
        del actor_id
        self.queries.append(request)
        return self.evidence


class FakeAssistantReadPort:
    def __init__(self) -> None:
        self.calls: list[AssistantToolCall] = []

    async def execute(
        self,
        call: AssistantToolCall,
        *,
        actor_id: UUID,
    ) -> AssistantToolObservation:
        del actor_id
        self.calls.append(call)
        return AssistantToolObservation(
            tool_call_id=call.id,
            name=call.name,
            found=True,
            content=f"{call.name} 已执行",
            data={},
        )


class FakeShipmentWorkflowPort:
    def __init__(self, progress: DraftProgress) -> None:
        self.progress = progress
        self.draft_calls: list[DraftToolCall] = []

    async def load_progress(
        self, conversation_id: UUID, actor_id: UUID
    ) -> DraftProgress:
        del conversation_id, actor_id
        return self.progress

    async def execute_draft_tool(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        call: DraftToolCall,
    ) -> DraftProgress:
        del conversation_id, actor_id
        self.draft_calls.append(call)
        return self.progress

    async def validate_and_quote(
        self, conversation_id: UUID, actor_id: UUID
    ) -> QuoteProgress:
        del conversation_id, actor_id
        raise NotImplementedError

    async def prepare_confirmation(
        self, conversation_id: UUID, actor_id: UUID
    ) -> ConfirmationSnapshot:
        del conversation_id, actor_id
        raise NotImplementedError

    async def create_confirmed(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        request_id: str,
    ) -> ShipmentReceipt:
        del conversation_id, actor_id, request_id
        raise NotImplementedError


class FakeConversationPort:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def load_history(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        del conversation_id, actor_id
        return self.messages[-limit:]

    async def append_message(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        *,
        role: str,
        content: str,
        envelope: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del conversation_id, actor_id
        message: dict[str, object] = {
            "role": role,
            "content": content,
            "envelope": envelope,
        }
        self.messages.append(message)
        return message


class FakeTracePort:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record(self, event: str, **payload: object) -> None:
        self.events.append((event, payload))

    def summary(self) -> dict[str, object]:
        return {"events": self.events}
