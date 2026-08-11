import json
from math import isclose

import httpx
import pytest

from yitu.knowledge.embedding import (
    DeterministicEmbedding,
    EmbeddingPermanentError,
    EmbeddingRetryableError,
    QwenEmbeddingProvider,
    get_embedding_provider,
)
from yitu.platform.config import Settings


def error_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={
            "error": {
                "message": "upstream failure",
                "type": "server_error",
                "code": None,
            }
        },
    )


def test_qwen_batches_preserves_order_and_normalizes_vectors() -> None:
    batch_sizes: list[int] = []
    authorization_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        texts = payload["input"]
        batch_sizes.append(len(texts))
        authorization_headers.append(request.headers.get("authorization"))
        data = [
            {"index": index, "embedding": [float(index + 1), 1.0]}
            for index in reversed(range(len(texts)))
        ]
        return httpx.Response(
            200,
            json={"object": "list", "model": payload["model"], "data": data},
        )

    provider = QwenEmbeddingProvider(
        "https://qwen.test/compatible-mode/v1",
        "test-api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        vectors = provider.embed([f"文本-{index}" for index in range(33)])
    finally:
        provider.close()

    assert batch_sizes == [32, 1]
    assert authorization_headers == ["Bearer test-api-key", "Bearer test-api-key"]
    assert len(vectors) == 33
    assert provider.dimension == 2
    assert vectors[0] == pytest.approx([2**-0.5, 2**-0.5])
    assert vectors[1][0] > vectors[0][0]
    assert all(isclose(sum(value * value for value in vector), 1.0) for vector in vectors)


def test_qwen_rejects_empty_response_and_dimension_drift() -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                json={"object": "list", "model": "qwen", "data": []},
            ),
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": "qwen",
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                },
            ),
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": "qwen",
                    "data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}],
                },
            ),
        ]
    )
    provider = QwenEmbeddingProvider(
        "https://qwen.test/v1",
        "test-api-key",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: next(responses))
        ),
    )
    try:
        with pytest.raises(EmbeddingPermanentError, match="response"):
            provider.embed(["空响应"])
        assert provider.embed(["二维向量"]) == [[1.0, 0.0]]
        with pytest.raises(EmbeddingPermanentError, match="dimension"):
            provider.embed(["维度漂移"])
    finally:
        provider.close()


@pytest.mark.parametrize("status_code", [429, 500])
def test_qwen_maps_retry_exhaustion_to_stable_error(status_code: int) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return error_response(status_code)

    provider = QwenEmbeddingProvider(
        "https://qwen.test/v1",
        "test-api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(EmbeddingRetryableError) as error:
            provider.embed(["不得进入异常的正文"])
    finally:
        provider.close()

    assert request_count == 3
    assert "正文" not in str(error.value)
    assert "test-api-key" not in str(error.value)


def test_qwen_maps_4xx_to_permanent_error_without_retry() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return error_response(400)

    provider = QwenEmbeddingProvider(
        "https://qwen.test/v1",
        "test-api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(EmbeddingPermanentError):
            provider.embed(["invalid"])
    finally:
        provider.close()
    assert request_count == 1


def test_embedding_factory_selects_local_or_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_settings = Settings(embedding_provider="local")
    monkeypatch.setattr(
        "yitu.knowledge.embedding.get_settings",
        lambda: local_settings,
    )
    assert isinstance(get_embedding_provider(), DeterministicEmbedding)

    qwen_settings = Settings(
        embedding_provider="qwen",
        embedding_base_url="https://qwen.test/v1",
        embedding_api_key="test-api-key",
    )
    monkeypatch.setattr(
        "yitu.knowledge.embedding.get_settings",
        lambda: qwen_settings,
    )
    provider = get_embedding_provider()
    assert isinstance(provider, QwenEmbeddingProvider)
    assert provider.model == "qwen3.7-text-embedding"
    provider.close()
