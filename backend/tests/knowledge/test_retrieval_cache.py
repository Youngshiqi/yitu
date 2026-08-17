"""查询向量 LRU 缓存的行为契约。"""

from yitu.knowledge.embedding import DeterministicEmbedding
from yitu.knowledge.retrieval import _embed_query_cached


class CountingProvider(DeterministicEmbedding):
    """DeterministicEmbedding 的计数包装，验证缓存命中效果。"""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return super().embed(texts)


def test_same_query_hits_cache() -> None:
    provider = CountingProvider()
    first = _embed_query_cached(provider, "电脑能不能寄")
    second = _embed_query_cached(provider, "电脑能不能寄")
    assert first == second
    assert provider.calls == 1


def test_distinct_provider_instances_do_not_share_cache() -> None:
    a = CountingProvider()
    b = CountingProvider()
    _embed_query_cached(a, "同一个问题")
    _embed_query_cached(b, "同一个问题")
    assert a.calls == 1
    assert b.calls == 1
