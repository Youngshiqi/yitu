"""模型调用前的上下文组装器，只发送最小且已脱敏的内容。"""

from collections.abc import Sequence

from yitu.agent.model_adapter import ModelMessage
from yitu.agent.privacy import redact_text
from yitu.agent.prompts import SYSTEM_PROMPT

_MAX_TOOL_RESULT = 8000
_TRUNCATION_NOTE = "…(超长截断)"


def _truncate(value: str, limit: int = _MAX_TOOL_RESULT) -> str:
    """超限时在最后一个完整 JSON 闭合边界处截断，避免残缺结构误导模型。"""
    if len(value) <= limit:
        return value
    cut = value[:limit]
    # 只在成对的闭合符处收口；找不到可靠边界时退回硬截断。
    boundary = max(cut.rfind("}"), cut.rfind("]"))
    if boundary > limit // 2:
        return cut[: boundary + 1] + _TRUNCATION_NOTE
    return cut + _TRUNCATION_NOTE


def build_model_context(history: Sequence[ModelMessage], memories: Sequence[str] = (), tool_results: Sequence[str] = ()) -> list[ModelMessage]:
    """组合最近消息和持久记忆，限制长度并执行二次脱敏。"""
    # 平台身份必须始终位于首条系统消息，不能被历史消息或用户偏好覆盖。
    result: list[ModelMessage] = [
        ModelMessage(role="system", content=SYSTEM_PROMPT.strip())
    ]
    if memories:
        result.append(ModelMessage(role="system", content=redact_text("用户偏好：" + "；".join(memories[:10]))))
    for tool_result in tool_results:
        result.append(ModelMessage(role="system", content=redact_text("工具执行结果：" + _truncate(tool_result))))
    for message in history[-20:]:
        result.append(ModelMessage(role=message.role, content=redact_text(_truncate(message.content))))
    return result
