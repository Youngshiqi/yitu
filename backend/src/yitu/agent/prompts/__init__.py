"""Agent 提示词公开入口。

具体提示词按职责放在同目录模块中；旧的 ``yitu.agent.prompts`` 导入路径
仍然由本包提供，避免影响现有节点和扩展。
"""

from yitu.agent.prompts.assistant import (
    BUDGET_REFUSAL,
    CROSS_USER_REFUSAL,
    DRAFT_LOOP_PROMPT,
    INJECTION_REFUSAL,
    KNOWLEDGE_ANSWER_PROMPT,
    KNOWLEDGE_NOT_FOUND_REPLY,
    SYSTEM_PROMPT,
    TIMEOUT_REFUSAL,
)

__all__ = [
    "BUDGET_REFUSAL",
    "CROSS_USER_REFUSAL",
    "DRAFT_LOOP_PROMPT",
    "INJECTION_REFUSAL",
    "KNOWLEDGE_ANSWER_PROMPT",
    "KNOWLEDGE_NOT_FOUND_REPLY",
    "SYSTEM_PROMPT",
    "TIMEOUT_REFUSAL",
]
