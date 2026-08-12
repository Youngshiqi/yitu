import re

import jieba  # type: ignore[import-untyped]

TOKENIZER_VERSION = "jieba-0.42.1-search-v1"
TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize_for_search(text: str) -> str:
    """将中文内容转换为空格分隔检索词，供 PostgreSQL simple 配置索引。"""
    normalized = text.strip().lower()
    if not normalized:
        return ""
    # cut_for_search 会补充长词的短词组合，兼顾规则名称和用户口语查询。
    tokens = (
        token.strip()
        for token in jieba.cut_for_search(normalized)
        if TOKEN_RE.fullmatch(token.strip())
    )
    return " ".join(dict.fromkeys(token for token in tokens if token))
