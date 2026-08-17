"""RAG 检索证据接入知识回复的结构化与「无证据不编造」契约。"""

from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete

from yitu.agent.model_adapter import (
    ModelMessage,
    StructuredT,
    ToolCallResult,
    ToolStreamEvent,
)
from yitu.agent.models import AgentConversation
from yitu.agent.prompts import KNOWLEDGE_ANSWER_PROMPT, KNOWLEDGE_NOT_FOUND_REPLY
from yitu.agent.service import (
    AgentConversationService,
    _format_knowledge_evidence,
)
from yitu.agent.tools.base import ToolResult
from yitu.agent.tools.knowledge import (
    KnowledgeCitation,
    KnowledgeSearchResult,
)
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory


def _citation() -> KnowledgeCitation:
    return KnowledgeCitation(
        document_id=uuid4(),
        filename="禁寄规则.pdf",
        index_version=3,
        title="禁止寄递物品指导目录",
        section_path=["第一章", "禁寄物品"],
        page_start=2,
        page_end=3,
        content="枪支（含仿制品）、弹药。",
        score=0.91,
    )


def test_format_knowledge_evidence_renders_source_and_content() -> None:
    text = _format_knowledge_evidence([_citation()])
    assert "枪支" in text
    assert "禁止寄递物品指导目录" in text
    assert "禁寄规则.pdf" in text
    assert "第一章" in text
    assert "第2-3页" in text
    # 不夹带工具信封元数据，避免模型被 JSON 噪声干扰。
    assert '"tool"' not in text
    assert '"found"' not in text


class RecordingAdapter:
    """记录模型收到的消息，验证证据与指令确实进入上下文。"""

    def __init__(self) -> None:
        self.last_messages: list[ModelMessage] | None = None
        self.stream_calls = 0

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        del messages
        raise AssertionError("知识回复阶段应使用流式接口")

    async def complete_structured(
        self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
    ) -> StructuredT:
        del messages, response_model
        raise AssertionError("知识回复阶段不应调用结构化理解")

    async def complete_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> ToolCallResult:
        del messages, tools
        raise AssertionError("知识回复阶段不应调用工具循环")

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        self.stream_calls += 1
        self.last_messages = list(messages)
        yield "已生成回答"

    async def stream_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> AsyncIterator[ToolStreamEvent]:
        del messages, tools
        raise AssertionError("知识回复阶段不应调用工具流式接口")


@pytest.mark.asyncio
async def test_knowledge_reply_injects_evidence_and_prompt() -> None:
    adapter = RecordingAdapter()
    service = AgentConversationService(session=SimpleNamespace())  # type: ignore[arg-type]
    chunks = [
        chunk
        async for chunk in service._stream_knowledge_reply(
            adapter, [], [], [_citation()]
        )
    ]

    assert "".join(chunks) == "已生成回答"
    assert adapter.stream_calls == 1
    assert adapter.last_messages is not None
    joined = "\n".join(message.content for message in adapter.last_messages)
    assert "【知识证据】" in joined
    assert "枪支" in joined
    assert KNOWLEDGE_ANSWER_PROMPT.split("\n")[0] in joined


class ScriptedKnowledgeModel:
    """意图识别固定为 KNOWLEDGE_QUERY，complete 计数以断言无证据时不调用模型。"""

    def __init__(self) -> None:
        self.complete_calls = 0

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        self.complete_calls += 1
        return "不应被调用"

    async def complete_structured(
        self, messages: Sequence[ModelMessage], response_model: type[StructuredT]
    ) -> StructuredT:
        del messages
        return response_model.model_validate(
            {
                "intents": ["KNOWLEDGE_QUERY"],
                "primary_intent": "KNOWLEDGE_QUERY",
                "confidence": 0.95,
                "knowledge_query": "禁止寄递物品",
                "draft": {},
            }
        )

    async def complete_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> ToolCallResult:
        del messages, tools
        raise AssertionError("知识查询不应进入草稿工具循环")

    def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        del messages

        async def empty() -> AsyncIterator[str]:
            if False:
                yield ""

        return empty()

    async def stream_with_tools(
        self, messages: Sequence[ModelMessage], tools: Sequence[dict[str, object]]
    ) -> AsyncIterator[ToolStreamEvent]:
        del messages, tools
        raise AssertionError("知识查询不应进入草稿工具循环")


@pytest.mark.asyncio
async def test_knowledge_no_evidence_returns_fixed_reply_without_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        owner_row = next(user for user in users if user.demo_key == "customer")
        owner = CurrentUser(owner_row.id, Role.CUSTOMER, None)

    async def fake_execute(
        tool_self: object,
        request: object,
        context: object,
    ) -> ToolResult[KnowledgeSearchResult]:
        del tool_self, request, context
        return ToolResult(
            tool="knowledge_search",
            found=False,
            data=KnowledgeSearchResult(citations=[]),
            message="没有找到足够的已发布知识证据。",
        )

    monkeypatch.setattr(
        "yitu.agent.service.KnowledgeSearchTool.execute",
        fake_execute,
    )

    model = ScriptedKnowledgeModel()
    conversation: AgentConversation
    async with SessionFactory() as session:
        service = AgentConversationService(session)
        conversation = await service.create(owner)
        turn = await service.send_message(
            conversation.id, owner, "哪些物品禁止寄递", model
        )

    assert model.complete_calls == 0
    assert turn.assistant_message.content == KNOWLEDGE_NOT_FOUND_REPLY

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(AgentConversation).where(AgentConversation.id == conversation.id)
        )
