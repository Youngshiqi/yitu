"""查询分词与列举型查询改写的单元测试。"""

from yitu.knowledge.tokenization import (
    CATALOG_ANCHORS,
    expand_query_tokens,
    tokenize_for_query,
    tokenize_for_search,
)


def test_tokenize_for_search_keeps_content_tokens() -> None:
    tokens = tokenize_for_search("禁止寄递物品")
    assert "禁止" in tokens.split()
    assert "寄递" in tokens.split()
    assert "物品" in tokens.split()


def test_tokenize_for_query_filters_interrogatives() -> None:
    tokens = tokenize_for_query("哪些物品禁止寄递")
    assert "哪些" not in tokens.split()
    assert "物品" in tokens.split()
    assert "禁止" in tokens.split()
    assert "寄递" in tokens.split()


def test_tokenize_for_query_returns_empty_for_pure_stopwords() -> None:
    assert tokenize_for_query("哪些") == ""
    assert tokenize_for_query("吗呢") == ""


def test_expand_query_tokens_appends_catalog_anchors_for_enumeration() -> None:
    query = "哪些物品禁止寄递"
    tokens = tokenize_for_query(query)
    expanded = expand_query_tokens(query, tokens)
    expanded_tokens = expanded.split()
    for anchor in CATALOG_ANCHORS:
        assert anchor in expanded_tokens
    for token in tokens.split():
        assert token in expanded_tokens


def test_expand_query_tokens_noop_for_non_enumeration() -> None:
    query = "北京到上海寄递时效"
    tokens = tokenize_for_query(query)
    assert expand_query_tokens(query, tokens) == tokens
