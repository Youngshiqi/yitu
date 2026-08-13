"""可替换的 Agent 对话模型适配器。"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from yitu.platform.config import get_settings

StructuredT = TypeVar("StructuredT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """发送给模型的最小消息结构。"""

    role: str
    content: str


class ModelAdapter(Protocol):
    """隔离具体云模型 SDK，便于固定模型和生产模型互换。"""

    async def complete(self, messages: Sequence[ModelMessage]) -> str: ...

    async def complete_structured(
        self,
        messages: Sequence[ModelMessage],
        response_model: type[StructuredT],
    ) -> StructuredT: ...

    def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]: ...


class ModelUnavailableError(RuntimeError):
    """表示模型配置缺失或服务暂时不可用。"""


class FixedModelAdapter:
    """供本地开发和自动化验证使用的确定性模型。"""

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        last_user = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        return f"已收到你的消息：{last_user}"

    async def complete_structured(
        self,
        messages: Sequence[ModelMessage],
        response_model: type[StructuredT],
    ) -> StructuredT:
        """固定适配器不猜测业务意图，只返回低置信度普通对话结果。"""
        return response_model.model_validate(
            {
                "intents": ["GENERAL_CHAT"],
                "primary_intent": "GENERAL_CHAT",
                "confidence": 0.0,
                "draft": {},
            }
        )

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        yield await self.complete(messages)


class OpenAICompatibleModelAdapter:
    """通过 OpenAI 兼容接口调用生产聊天模型。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("Agent model configuration is incomplete")
        self._model = model
        self._client = AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=2,
        )

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        """返回完整回复，并把上游故障折叠为不含提示词的稳定异常。"""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._request_messages(messages),
            )
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ModelUnavailableError("Agent model returned an empty response")
        return content

    async def complete_structured(
        self,
        messages: Sequence[ModelMessage],
        response_model: type[StructuredT],
    ) -> StructuredT:
        """优先使用 Function Calling；供应商不兼容时降级为 JSON Mode。"""
        function_name = "classify_logistics_intent"
        tools = cast(
            Any,
            [
                {
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "description": "返回物流意图、槽位和置信度",
                        "parameters": response_model.model_json_schema(),
                    },
                }
            ],
        )
        try:
            for _attempt in range(2):
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=self._request_messages(messages),
                    tools=tools,
                    tool_choice=cast(
                        Any,
                        {"type": "function", "function": {"name": function_name}},
                    ),
                )
                if not response.choices:
                    continue
                message = response.choices[0].message
                arguments = message.content
                if message.tool_calls:
                    first_call = message.tool_calls[0]
                    if first_call.type == "function":
                        arguments = first_call.function.arguments
                # 少数 OpenAI-compatible 服务忽略 tool_choice 而返回 JSON 文本，保留兼容降级。
                if not arguments:
                    continue
                try:
                    return response_model.model_validate_json(arguments)
                except ValidationError:
                    continue
        except APIStatusError:
            # 部分 OpenAI-compatible 模型不支持 tools/tool_choice，改用 JSON Mode。
            pass
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None
        return await self._complete_json_mode(messages, response_model)

    async def _complete_json_mode(
        self,
        messages: Sequence[ModelMessage],
        response_model: type[StructuredT],
    ) -> StructuredT:
        """Function Calling 不可用时，以 JSON Mode 保持相同输出契约。"""
        schema_instruction = ModelMessage(
            role="system",
            content=(
                "只输出一个 JSON 对象，必须符合以下 JSON Schema："
                + response_model.model_json_schema().__str__()
            ),
        )
        request_messages = [*messages, schema_instruction]
        try:
            for _attempt in range(2):
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=self._request_messages(request_messages),
                    response_format={"type": "json_object"},
                )
                content = (
                    response.choices[0].message.content if response.choices else None
                )
                if not content:
                    continue
                try:
                    return response_model.model_validate_json(content)
                except ValidationError:
                    continue
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None
        raise ModelUnavailableError("Agent model returned invalid structured output")

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        """按上游增量返回文本；调用方负责持久化最终消息。"""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._request_messages(messages),
                stream=True,
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None

    @staticmethod
    def _request_messages(
        messages: Sequence[ModelMessage],
    ) -> list[ChatCompletionMessageParam]:
        """在适配器边界把内部稳定消息转换为 SDK 联合类型。"""
        return cast(
            list[ChatCompletionMessageParam],
            [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        )


def get_model_adapter() -> ModelAdapter:
    """根据配置选择固定模型或 OpenAI 兼容生产模型。"""
    settings = get_settings()
    provider = settings.agent_model_provider.strip().lower()
    if provider == "fixed":
        return FixedModelAdapter()
    # DeepSeek 使用 OpenAI-compatible 协议，允许配置文件使用供应商名称。
    if provider not in {"openai-compatible", "deepseek"}:
        raise ModelUnavailableError("Agent model provider is unsupported")
    if not settings.agent_model_base_url or not settings.agent_model_api_key:
        raise ModelUnavailableError("Agent model configuration is incomplete")
    return OpenAICompatibleModelAdapter(
        base_url=settings.agent_model_base_url,
        api_key=settings.agent_model_api_key,
        model=settings.agent_model_name,
        timeout_seconds=settings.agent_model_timeout_seconds,
    )
