"""模型能力端口，不暴露供应商 SDK。"""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from yitu.agent.model_adapter import ModelMessage, ToolStreamEvent


class ModelPort(Protocol):
    def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]: ...
