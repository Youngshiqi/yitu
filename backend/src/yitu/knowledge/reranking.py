"""精排模型 Provider：使用专用重排序模型替代 LLM 精排，大幅降低成本。

Bailian 的 gte-rerank 模型按 token 计费，价格远低于对话模型，
且专为相关性排序优化，延迟更低、排序更稳定。
"""

import logging
from typing import Protocol

import httpx

from yitu.platform.config import get_settings

logger = logging.getLogger(__name__)

_RERANK_BATCH_SIZE = 25


class RerankRetryableError(RuntimeError):
    """表示限流、网络或模型服务故障，可由调用方退避重试。"""


class RerankPermanentError(RuntimeError):
    """表示配置、请求或响应不可恢复。"""


class RerankProvider(Protocol):
    """对查询-文档对计算相关性分数，返回按分数降序排列的索引。"""

    @property
    def model(self) -> str: ...

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]: ...


class DeterministicReranker:
    """仅供开发和自动化测试使用的确定性精排器。

    始终返回原始顺序，分数恒为 1.0。
    """

    model = "deterministic-test"

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        return [(i, 1.0) for i in range(min(len(documents), top_n))]


class BailianRerankProvider:
    """通过阿里云百炼 DashScope 兼容接口调用 gte-rerank 精排模型。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gte-rerank",
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("Rerank base URL and API key are required")

        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        """对文档列表按相关性精排，返回 (原始索引, 分数) 的降序列表。"""
        if not documents:
            return []

        all_results: list[tuple[int, float]] = []
        for start in range(0, len(documents), _RERANK_BATCH_SIZE):
            batch = documents[start : start + _RERANK_BATCH_SIZE]
            all_results.extend(self._rerank_batch(query, batch, start))

        all_results.sort(key=lambda item: item[1], reverse=True)
        return all_results[:top_n]

    def _rerank_batch(
        self, query: str, documents: list[str], offset: int
    ) -> list[tuple[int, float]]:
        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": len(documents),
            },
        }
        try:
            response = self._client.post(
                "/rerank",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (429, 500, 502, 503):
                raise RerankRetryableError(
                    "Rerank service is temporarily unavailable"
                ) from exc
            raise RerankPermanentError(
                f"Rerank request was rejected (status={status})"
            ) from exc
        except (httpx.NetworkError, httpx.TimeoutException) as exc:
            raise RerankRetryableError(
                "Rerank service is temporarily unavailable"
            ) from exc

        results = body.get("output", {}).get("results", [])
        if not isinstance(results, list):
            raise RerankPermanentError("Rerank response format is invalid")

        parsed: list[tuple[int, float]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            score = item.get("relevance_score")
            if isinstance(index, int) and isinstance(score, (int, float)):
                parsed.append((offset + index, float(score)))

        if not parsed:
            raise RerankPermanentError("Rerank response contains no valid results")

        logger.info(
            "精排完成 model=%s query_len=%s doc_count=%s top_score=%.4f",
            self.model,
            len(query),
            len(parsed),
            parsed[0][1] if parsed else 0,
        )
        return parsed


def get_rerank_provider() -> RerankProvider:
    """根据运行配置选择生产 Bailian 或本地确定性精排器。"""
    settings = get_settings()
    if settings.rerank_provider == "local":
        return DeterministicReranker()
    if settings.rerank_provider != "bailian":
        raise RuntimeError("Unsupported rerank provider")
    if not settings.rerank_base_url or not settings.rerank_api_key:
        raise RuntimeError("Rerank configuration is incomplete")
    return BailianRerankProvider(
        settings.rerank_base_url,
        settings.rerank_api_key,
        settings.rerank_model,
    )