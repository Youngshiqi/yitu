"""Agent 模型调用前的确定性隐私脱敏。"""

import re

_SECRET_PATTERNS = (
    (re.compile(r"\b(?:sk|AKID)[A-Za-z0-9_-]{12,}\b"), "[密钥已隐藏]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "[令牌已隐藏]",
    ),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号已隐藏]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[邮箱已隐藏]"),
)


def redact_text(value: str) -> str:
    """隐藏密钥、令牌、手机号和邮箱，保留业务语义。"""
    result = value
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def contains_forbidden_memory(value: str) -> bool:
    """拒绝把明显的密钥、令牌或联系方式写入持久记忆。"""
    return redact_text(value) != value
