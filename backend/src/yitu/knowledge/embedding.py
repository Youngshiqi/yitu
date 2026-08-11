import logging
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import Protocol

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from yitu.platform.config import get_settings

logger = logging.getLogger(__name__)

QWEN_BATCH_SIZE = 32
QWEN_EMBEDDING_DIMENSION = 1024


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int | None: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingRetryableError(RuntimeError):
    """表示限流、网络或模型服务故障，可由 Worker 退避重试。"""


class EmbeddingPermanentError(RuntimeError):
    """表示配置、请求或向量响应不可恢复。"""


class DeterministicEmbedding:
    """仅供开发和自动化测试使用的确定性向量实现。"""

    model = "deterministic-test"
    dimension = QWEN_EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            data = text.encode("utf-8")
            # 测试向量也保持 1024 维，确保 CI 能覆盖真实 pgvector 列约束。
            digest = b"".join(
                sha256(counter.to_bytes(4, "big") + data).digest()
                for counter in range(self.dimension // 32)
            )
            vector = [
                ((byte / 255.0) * 2.0) - 1.0
                for byte in digest[: self.dimension]
            ]
            norm = sqrt(fsum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class QwenEmbeddingProvider:
    """通过阿里云百炼 OpenAI 兼容接口批量生成 Qwen 文本向量。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen3.7-text-embedding",
        *,
        expected_dimension: int | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("Qwen embedding base URL and API key are required")
        if expected_dimension is not None and expected_dimension <= 0:
            raise ValueError("Qwen embedding dimension must be positive")

        self.model = model
        self._dimension = expected_dimension
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=60.0,
            max_retries=2,
            http_client=http_client,
        )

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def close(self) -> None:
        """关闭 SDK 持有的同步 HTTP 连接池。"""
        self._client.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """按 32 条分批生成向量，并保持与输入文本相同的顺序。"""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), QWEN_BATCH_SIZE):
            batch = texts[start : start + QWEN_BATCH_SIZE]
            vectors.extend(self._embed_batch(batch))

        logger.info(
            "生成 Qwen 向量 model=%s dimension=%s count=%s",
            self.model,
            self._dimension,
            len(vectors),
        )
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=texts,
            )
        except (APIConnectionError, RateLimitError, InternalServerError):
            # SDK 已完成内部重试，此处只向 Worker 暴露稳定且不含正文的错误。
            raise EmbeddingRetryableError(
                "Qwen embedding service is temporarily unavailable"
            ) from None
        except APIStatusError:
            raise EmbeddingPermanentError(
                "Qwen embedding request was rejected"
            ) from None
        except ValueError:
            # OpenAI SDK 会在空 data 等响应解析失败时直接抛出 ValueError。
            raise EmbeddingPermanentError(
                "Qwen embedding response is invalid"
            ) from None
        except OpenAIError:
            raise EmbeddingPermanentError("Qwen embedding request failed") from None

        ordered = sorted(response.data, key=lambda item: item.index)
        indexes = [item.index for item in ordered]
        if indexes != list(range(len(texts))):
            raise EmbeddingPermanentError(
                "Qwen embedding response indexes are invalid"
            )

        return [self._normalize(item.embedding) for item in ordered]

    def _normalize(self, embedding: list[float]) -> list[float]:
        if not embedding or not all(isfinite(value) for value in embedding):
            raise EmbeddingPermanentError(
                "Qwen embedding response contains invalid values"
            )

        dimension = len(embedding)
        if self._dimension is None:
            # 首次有效响应锁定维度，后续批次和请求必须保持一致。
            self._dimension = dimension
        elif dimension != self._dimension:
            raise EmbeddingPermanentError("Qwen embedding dimension changed")

        norm = sqrt(fsum(value * value for value in embedding))
        if norm == 0:
            raise EmbeddingPermanentError("Qwen embedding response is a zero vector")
        return [value / norm for value in embedding]


def get_embedding_provider() -> EmbeddingProvider:
    """根据运行配置选择生产 Qwen 或本地确定性 Provider。"""
    settings = get_settings()
    if settings.embedding_provider == "local":
        return DeterministicEmbedding()
    if settings.embedding_provider != "qwen":
        raise RuntimeError("Unsupported embedding provider")
    if not settings.embedding_base_url or not settings.embedding_api_key:
        raise RuntimeError("Qwen embedding configuration is incomplete")
    return QwenEmbeddingProvider(
        settings.embedding_base_url,
        settings.embedding_api_key,
        settings.embedding_model,
        expected_dimension=settings.embedding_dimension,
    )
