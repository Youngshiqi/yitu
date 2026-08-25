"""基于对话模型的 RAG 增强：查询改写与候选精排。

两者都遵循同一原则——失败/超时时回退原始输入，绝不阻塞检索主链路。
"""

import asyncio
import json
import re
from collections.abc import Sequence
from functools import lru_cache

from yitu.agent.infrastructure.model_adapter import (
    ModelAdapter,
    ModelMessage,
    ModelUnavailableError,
    get_model_adapter,
)
from yitu.knowledge.retrieval import Evidence
from yitu.platform.config import get_settings

# 改写/精排都是增强路径，超时预算必须小于主模型超时。
REWRITE_TIMEOUT_SECONDS = 4.0
RERANK_TIMEOUT_SECONDS = 6.0
# 精排时每条候选喂给模型的正文长度，控制 token 成本。
_RERANK_SNIPPET_CHARS = 280
_MAX_QUERY_CHARS = 200
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


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


class LLMReranker:
    """让对话模型对融合候选打分重排，未打分候选沉底并保持相对顺序。"""

    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    async def rerank(self, query: str, candidates: list[Evidence]) -> list[Evidence]:
        if not candidates:
            return candidates
        lines = [
            f"{index}. {item.content[:_RERANK_SNIPPET_CHARS]}"
            for index, item in enumerate(candidates)
        ]
        messages: Sequence[ModelMessage] = [
            ModelMessage(
                role="system",
                content=(
                    "你是检索结果精排器。给定查询和候选片段列表，"
                    "为每个候选输出 0 到 1 的相关性分数（1 最相关）。"
                    '只输出 JSON：{"scores": [{"index": 0, "score": 0.9}, ...]}，'
                    "不要输出其他内容。"
                ),
            ),
            ModelMessage(
                role="user",
                content=f"查询：{query}\n候选片段：\n" + "\n".join(lines),
            ),
        ]
        try:
            raw = await asyncio.wait_for(
                self.adapter.complete(messages), timeout=RERANK_TIMEOUT_SECONDS
            )
            match = _JSON_OBJECT_RE.search(raw)
            if match is None:
                return candidates
            payload = json.loads(match.group(0))
            scores = {
                int(item["index"]): float(item["score"])
                for item in payload.get("scores", [])
                if isinstance(item, dict) and "index" in item and "score" in item
            }
        except Exception:  # noqa: BLE001 - 解析失败保持融合排序
            return candidates
        # 未被打分的候选得 -1 沉底；同分保持稳定（Python sort 稳定）。
        order = sorted(range(len(candidates)), key=lambda i: -scores.get(i, -1.0))
        return [candidates[i] for i in order]


@lru_cache(maxsize=1)
def build_rag_enhancements() -> tuple[LLMQueryRewriter | None, LLMReranker | None]:
    """生产模型可用时返回（改写器, 精排器）；固定模型或未配置时返回 (None, None)。

    lru_cache 单例化，避免每次检索新建底层 HTTP 客户端。
    """
    try:
        adapter = get_model_adapter()
    except ModelUnavailableError:
        return None, None
    if get_settings().agent_model_provider.strip().lower() == "fixed":
        return None, None
    return LLMQueryRewriter(adapter), LLMReranker(adapter)
