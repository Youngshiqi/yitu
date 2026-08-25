"""可替换的 Agent 对话模型适配器。"""

import json
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
class ToolCall:
    """模型在工具调用循环中产出的单次工具调用。"""

    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """complete_with_tools 的结果：纯文本和/或工具调用。"""

    content: str | None
    tool_calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class ToolStreamEvent:
    """stream_with_tools 产出的流式事件：内容增量或最终结果。

    delta 非空时为内容增量；result 非 None 时为最终结果（仅最后一个事件）。
    """

    delta: str = ""
    result: ToolCallResult | None = None


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """发送给模型的最小消息结构。"""

    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


class ModelAdapter(Protocol):
    """隔离具体云模型 SDK，便于固定模型和生产模型互换。"""

    async def complete(self, messages: Sequence[ModelMessage]) -> str: ...

    async def complete_structured(
        self,
        messages: Sequence[ModelMessage],
        response_model: type[StructuredT],
    ) -> StructuredT: ...

    async def complete_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> ToolCallResult: ...

    def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]: ...

    def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]: ...


class ModelUnavailableError(RuntimeError):
    """表示模型配置缺失或服务暂时不可用。"""


class FixedModelAdapter:
    """供本地开发和自动化验证使用的确定性模型。"""

    async def complete(self, messages: Sequence[ModelMessage]) -> str:
        last_user = next(
            (
                message.content
                for message in reversed(messages)
                if message.role == "user"
            ),
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

    async def complete_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> ToolCallResult:
        """固定适配器不调用工具，只返回空工具调用。"""
        del messages, tools
        return ToolCallResult(content=None, tool_calls=())

    async def stream(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        yield await self.complete(messages)

    async def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]:
        result = await self.complete_with_tools(messages, tools)
        if result.content:
            yield ToolStreamEvent(delta=result.content)
        yield ToolStreamEvent(result=result)


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

    async def complete_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> ToolCallResult:
        """调用带工具白名单的模型，模型可返回纯文本或工具调用。"""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._request_messages(messages),
                tools=cast(Any, list(tools)),
                tool_choice="auto",
            )
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None
        if not response.choices:
            raise ModelUnavailableError("Agent model returned an empty response")
        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or ():
            if call.type != "function":
                continue
            arguments = call.function.arguments or "{}"
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=parsed,
                )
            )
        return ToolCallResult(
            content=message.content,
            tool_calls=tuple(tool_calls),
        )

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

    async def stream_with_tools(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[ToolStreamEvent]:
        """流式返回内容增量，同时累积工具调用；最终事件携带完整结果。

        内容增量即时 yield，工具调用在流结束后组装为 ToolCallResult。
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._request_messages(messages),
                tools=cast(Any, list(tools)),
                tool_choice="auto",
                stream=True,
            )
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None

        content_parts: list[str] = []
        # OpenAI 流式工具调用按 index 分片到达，需按索引累积 id/name/arguments。
        tool_acc: dict[int, dict[str, str]] = {}

        try:
            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    yield ToolStreamEvent(delta=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        slot = tool_acc.setdefault(
                            idx, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.type:
                            pass  # 固定为 "function"
                        if tc.function:
                            if tc.function.name:
                                slot["name"] = tc.function.name
                            if tc.function.arguments:
                                slot["arguments"] += tc.function.arguments
        except (
            APIConnectionError,
            RateLimitError,
            InternalServerError,
            APIStatusError,
            OpenAIError,
        ):
            raise ModelUnavailableError("Agent model is unavailable") from None

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            arguments = slot["arguments"] or "{}"
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            tool_calls.append(
                ToolCall(id=slot["id"], name=slot["name"], arguments=parsed)
            )

        yield ToolStreamEvent(
            result=ToolCallResult(
                content="".join(content_parts) or None,
                tool_calls=tuple(tool_calls),
            )
        )

    @staticmethod
    def _request_messages(
        messages: Sequence[ModelMessage],
    ) -> list[ChatCompletionMessageParam]:
        """在适配器边界把内部稳定消息转换为 SDK 联合类型。"""
        result: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            if message.tool_call_id is not None:
                item["tool_call_id"] = message.tool_call_id
            result.append(item)
        return cast(list[ChatCompletionMessageParam], result)


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
