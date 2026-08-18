"""法规条头与正文的切分规则：孤立条号行不得与正文分离成独立 chunk。"""

from yitu.knowledge.chunking import ChunkingPolicy


def _contents(text: str) -> list[str]:
    return [chunk.content for chunk in ChunkingPolicy().chunk(text)]


def test_clause_heading_merges_with_body_across_blank_line() -> None:
    text = "第四条\n\n禁止寄递下列物品：\n（一）易燃物品"
    contents = _contents(text)
    assert len(contents) == 1
    assert "第四条" in contents[0]
    assert "禁止寄递下列物品" in contents[0]


def test_clause_heading_with_punctuation_merges_with_body() -> None:
    text = "第十二条：\n\n（一）枪支弹药\n（二）管制刀具"
    contents = _contents(text)
    assert len(contents) == 1
    assert "第十二条" in contents[0]
    assert "枪支弹药" in contents[0]


def test_catalog_of_multiple_clauses_flushes_separately_from_body() -> None:
    text = "第一条\n第二条\n第三条\n\n正文内容"
    contents = _contents(text)
    assert len(contents) == 2
    assert "第三条" in contents[0]
    assert "正文内容" in contents[1]


def test_clause_with_inline_body_still_splits_on_blank_line() -> None:
    text = "第四条 禁止寄递下列物品\n\n下一条正文"
    contents = _contents(text)
    assert len(contents) == 2
    assert "禁止寄递下列物品" in contents[0]
    assert "下一条正文" in contents[1]


def test_arabic_numeral_clause_merges_with_body() -> None:
    text = "第3条\n\n禁止寄递下列物品"
    contents = _contents(text)
    assert len(contents) == 1
    assert "第3条" in contents[0]
