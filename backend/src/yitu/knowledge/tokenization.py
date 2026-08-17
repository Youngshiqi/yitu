import re

import jieba  # type: ignore[import-untyped]

TOKENIZER_VERSION = "jieba-0.42.1-search-v2"
TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

# 查询侧停用词：疑问代词与语气虚词在全文检索里只会制造零命中或噪声。
# 注意仅作用于查询分词，不作用于索引分词，避免破坏已发布文档的召回。
QUERY_STOPWORDS = frozenset(
    {
        "哪些",
        "什么",
        "啥",
        "有啥",
        "有什么",
        "有哪些",
        "哪种",
        "哪类",
        "哪个",
        "哪几种",
        "的",
        "了",
        "吗",
        "呢",
        "啊",
        "吧",
        "么",
        "嘛",
        "呀",
        "哦",
        "请问",
        "一下",
    }
)

# 列举型问句标记：命中即认为是「枚举清单」类问题，追加目录锚点词以偏向附录章节。
# 仅保留疑问代词型标记，避免「列出/列举」等祈使动词误伤非清单类问题。
ENUMERATION_MARKERS = (
    "哪些",
    "有哪些",
    "有什么",
    "哪几种",
    "哪类",
    "包含哪些",
    "包括哪些",
)

# 目录锚点词：与索引侧纳入的 title/section_path 配合，让目录章节 chunk 获得更高关键词排名。
CATALOG_ANCHORS = ("目录", "指导目录")


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


def tokenize_for_query(text: str) -> str:
    """查询侧分词：过滤疑问代词与语气虚词，避免 AND 或 OR 检索因停用词零命中。"""
    return " ".join(
        token
        for token in tokenize_for_search(text).split()
        if token not in QUERY_STOPWORDS
    )


def expand_query_tokens(query: str, query_tokens: str) -> str:
    """对列举型问句追加目录锚点词，偏向枚举清单类 chunk。"""
    if any(marker in query for marker in ENUMERATION_MARKERS):
        anchors = " ".join(CATALOG_ANCHORS)
        return f"{query_tokens} {anchors}".strip()
    return query_tokens
