"""模型调用前的上下文组装器，只发送最小且已脱敏的内容。"""

from collections.abc import Sequence

from yitu.agent.model_adapter import ModelMessage
from yitu.agent.privacy import redact_text


def build_model_context(history: Sequence[ModelMessage], memories: Sequence[str] = ()) -> list[ModelMessage]:
    """组合最近消息和持久记忆，限制长度并执行二次脱敏。"""
    result: list[ModelMessage] = []
    if memories:
        result.append(ModelMessage(role="system", content=redact_text("用户偏好：" + "；".join(memories[:10]))))
    for message in history[-20:]:
        result.append(ModelMessage(role=message.role, content=redact_text(message.content[:8000])))
    return result
