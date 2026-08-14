"""模型调用前的上下文组装器，只发送最小且已脱敏的内容。"""

from collections.abc import Sequence

from yitu.agent.model_adapter import ModelMessage
from yitu.agent.privacy import redact_text
from yitu.agent.prompts import SYSTEM_PROMPT


def build_model_context(history: Sequence[ModelMessage], memories: Sequence[str] = (), tool_results: Sequence[str] = ()) -> list[ModelMessage]:
    """组合最近消息和持久记忆，限制长度并执行二次脱敏。"""
    # 平台身份必须始终位于首条系统消息，不能被历史消息或用户偏好覆盖。
    result: list[ModelMessage] = [
        ModelMessage(role="system", content=SYSTEM_PROMPT.strip())
    ]
    if memories:
        result.append(ModelMessage(role="system", content=redact_text("用户偏好：" + "；".join(memories[:10]))))
    for tool_result in tool_results:
        result.append(ModelMessage(role="system", content=redact_text("工具执行结果：" + tool_result[:8000])))
    for message in history[-20:]:
        result.append(ModelMessage(role=message.role, content=redact_text(message.content[:8000])))
    return result
