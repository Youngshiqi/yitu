"""基于对话模型的查询改写 + 专用精排模型的候选重排序。

两者都遵循同一原则——失败/超时时回退原始输入，绝不阻塞检索主链路。
精排使用专用 cross-encoder 模型（如 gte-rerank），成本远低于 LLM 精排。
"""

import asyncio
from collections.abc import Sequence
from functools import lru_cache

from yitu.agent.infrastructure.model_adapter import (
    ModelAdapter,
    ModelMessage,
    ModelUnavailableError,
    get_model_adapter,
)
from yitu.knowledge.reranking import (
    RerankProvider,
    RerankPermanentError,
    RerankRetryableError,
    get_rerank_provider,
)
from yitu.knowledge.retrieval import Evidence
from yitu.platform.config import get_settings

# 改写超时预算必须小于主模型超时。
REWRITE_TIMEOUT_SECONDS = 4.0
# 精排 snippet 长度：控制每段正文喂给精排模型的字符数。
_RERANK_SNIPPET_CHARS = 280
_MAX_QUERY_CHARS = 200


class LLMQueryRewriter:
    """把口语化问题改写为关键词化检索查询，带超时与输出校验。"""

    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    async def rewrite(self, query: str) -> str:
        messages: Sequence[ModelMessage] = [
            ModelMessage(
                role="system",
                content=(
                    "你是快递知识库检索的查询改写器。把用户的口语化问题改写为"
                    "适合关键词+向量混合检索的查询：保留专有名词和物品名称，"
                    "补齐可以省略的领域词（如「不能寄」→「禁止寄递」），"
                    "去掉寒暄和无意义词。只输出改写后的查询本身，不要解释、"
                    "不要标点以外的任何附加内容。若查询已经足够明确，原样输出。"
                ),
            ),
            ModelMessage(role="user", content=query),
        ]
        try:
            raw = await asyncio.wait_for(
                self.adapter.complete(messages), timeout=REWRITE_TIMEOUT_SECONDS
            )
        except Exception:  # noqa: BLE001 - 任何失败回退原查询
            return query
        rewritten = raw.strip().strip('"').strip()
        if not rewritten or len(rewritten) > _MAX_QUERY_CHARS or "\n" in rewritten:
            return query
        return rewritten


class CrossEncoderReranker:
    """使用专用 cross-encoder 精排模型对候选按查询相关性重排序。

    与 LLM 精排相比：延迟更低、成本更低、排序更稳定。
    失败时回退融合排序，不阻塞检索主链路。
    """

    def __init__(self, provider: RerankProvider) -> None:
        self._provider = provider

    async def rerank(self, query: str, candidates: list[Evidence]) -> list[Evidence]:
        if not candidates:
            return candidates
        documents = [
            item.content[:_RERANK_SNIPPET_CHARS] for item in candidates
        ]
        try:
            scored = await asyncio.to_thread(
                self._provider.rerank, query, documents, len(candidates)
            )
        except (RerankRetryableError, RerankPermanentError):
            return candidates

        if not scored:
            return candidates

        # 未被打分的候选沉底；同分保持稳定（Python sort 稳定）。
        score_map = {index: score for index, score in scored}
        order = sorted(
            range(len(candidates)),
            key=lambda i: -score_map.get(i, -1.0),
        )
        return [candidates[i] for i in order]


@lru_cache(maxsize=1)
def build_rag_enhancements() -> tuple[LLMQueryRewriter | None, CrossEncoderReranker | None]:
    """生产模型可用时返回（改写器, 精排器）；固定模型或未配置时回退。

    lru_cache 单例化，避免每次检索新建底层 HTTP 客户端。
    精排器使用专用 cross-encoder 模型，不再依赖 LLM 打分。
    """
    try:
        adapter = get_model_adapter()
    except ModelUnavailableError:
        return None, None

    settings = get_settings()
    if settings.agent_model_provider.strip().lower() == "fixed":
        return None, None

    rewriter = LLMQueryRewriter(adapter)

    try:
        rerank_provider = get_rerank_provider()
    except RuntimeError:
        return rewriter, None

    return rewriter, CrossEncoderReranker(rerank_provider)