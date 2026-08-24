"""现有模型适配器到工作流模型端口的薄委托。"""

from collections.abc import AsyncIterator, Sequence

from yitu.agent.model_adapter import (
    ModelAdapter,
    ModelMessage,
    ToolStreamEvent,
)


class ModelAdapterPort:
    def __init__(self, adapter: ModelAdapter) -> None:
        self._adapter = adapter

    def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]:
        return self._adapter.stream_with_tools(messages, tools)
