"""RAG 增强组件（查询改写、LLM 精排、装配工厂）的回退行为测试。"""

import pytest

from yitu.agent.model_adapter import ModelMessage
from yitu.agent.rag_enhancements import (
    LLMQueryRewriter,
    LLMReranker,
    build_rag_enhancements,
)
from yitu.knowledge.retrieval import Evidence


def _evidence(content: str) -> Evidence:
    return Evidence(
        document_id="00000000-0000-0000-0000-000000000001",
        filename="doc.pdf",
        category=None,
        index_version=1,
        title=None,
        section_path=[],
        content_type="text",
        page_start=None,
        page_end=None,
        content=content,
        score=0.5,
    )


class ScriptedAdapter:
    """按脚本返回内容或抛错的固定适配器。"""

    def __init__(self, output: str | Exception) -> None:
        self.output = output

    async def complete(self, messages) -> str:  # noqa: ANN001
        del messages
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class TestLLMQueryRewriter:
    @pytest.mark.asyncio
    async def test_normal_rewrite(self) -> None:
        rewriter = LLMQueryRewriter(ScriptedAdapter("禁止寄递物品 锂电池 蓄电池"))
        assert await rewriter.rewrite("电脑里的电池能寄吗") == "禁止寄递物品 锂电池 蓄电池"

    @pytest.mark.asyncio
    async def test_wraps_quotes_and_whitespace(self) -> None:
        rewriter = LLMQueryRewriter(ScriptedAdapter('  "禁止寄递 蓄电池"  \n'))
        assert await rewriter.rewrite("电池") == "禁止寄递 蓄电池"

    @pytest.mark.asyncio
    async def test_empty_output_falls_back(self) -> None:
        rewriter = LLMQueryRewriter(ScriptedAdapter("   "))
        assert await rewriter.rewrite("电池能寄吗") == "电池能寄吗"

    @pytest.mark.asyncio
    async def test_multiline_or_overlong_falls_back(self) -> None:
        for output in ("第一行\n第二行", "词" * 500):
            rewriter = LLMQueryRewriter(ScriptedAdapter(output))
            assert await rewriter.rewrite("电池") == "电池"

    @pytest.mark.asyncio
    async def test_model_error_falls_back(self) -> None:
        rewriter = LLMQueryRewriter(ScriptedAdapter(RuntimeError("down")))
        assert await rewriter.rewrite("电池能寄吗") == "电池能寄吗"


class TestLLMReranker:
    @pytest.mark.asyncio
    async def test_reorders_by_score(self) -> None:
        payload = '{"scores": [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.8}]}'
        reranker = LLMReranker(ScriptedAdapter(payload))
        candidates = [_evidence(c) for c in ("甲", "乙", "丙")]
        ranked = await reranker.rerank("查询", candidates)
        assert [item.content for item in ranked] == ["丙", "甲", "乙"]

    @pytest.mark.asyncio
    async def test_unscored_candidates_sink_in_original_order(self) -> None:
        payload = '{"scores": [{"index": 1, "score": 1.0}]}'
        reranker = LLMReranker(ScriptedAdapter(payload))
        candidates = [_evidence(c) for c in ("甲", "乙", "丙")]
        ranked = await reranker.rerank("查询", candidates)
        assert [item.content for item in ranked] == ["乙", "甲", "丙"]

    @pytest.mark.asyncio
    async def test_json_in_prose_still_parsed(self) -> None:
        payload = '好的，结果如下：\n{"scores": [{"index": 0, "score": 1.0}]} 请参考。'
        reranker = LLMReranker(ScriptedAdapter(payload))
        candidates = [_evidence(c) for c in ("甲", "乙")]
        ranked = await reranker.rerank("查询", candidates)
        assert ranked[0].content == "甲"

    @pytest.mark.asyncio
    async def test_invalid_output_keeps_order(self) -> None:
        for output in ("完全不是JSON", '{"scores": "bad"}'):
            reranker = LLMReranker(ScriptedAdapter(output))
            candidates = [_evidence(c) for c in ("甲", "乙")]
            ranked = await reranker.rerank("查询", candidates)
            assert [item.content for item in ranked] == ["甲", "乙"]

    @pytest.mark.asyncio
    async def test_model_error_keeps_order(self) -> None:
        reranker = LLMReranker(ScriptedAdapter(RuntimeError("down")))
        candidates = [_evidence(c) for c in ("甲", "乙")]
        assert await reranker.rerank("查询", candidates) == candidates


def test_factory_disabled_for_fixed_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from yitu.platform.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "agent_model_provider", "fixed", raising=False)
    build_rag_enhancements.cache_clear()
    try:
        assert build_rag_enhancements() == (None, None)
    finally:
        build_rag_enhancements.cache_clear()


@pytest.mark.asyncio
async def test_rewriter_prompt_contains_user_query() -> None:
    captured: list[list[ModelMessage]] = []

    class CapturingAdapter:
        async def complete(self, messages) -> str:  # noqa: ANN001
            captured.append(list(messages))
            return "改写结果"

    rewriter = LLMQueryRewriter(CapturingAdapter())
    await rewriter.rewrite("电池能寄吗")
    user_messages = [m for m in captured[0] if m.role == "user"]
    assert user_messages and "电池能寄吗" in user_messages[0].content
