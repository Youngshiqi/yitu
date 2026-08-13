"""按 Fast Path / Slow Path 将自然语言转换为结构化物流意图。"""

import re
import unicodedata
from dataclasses import dataclass
from logging import ERROR
from typing import Literal

import jieba  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from yitu.agent.model_adapter import ModelAdapter, ModelMessage

IntentName = Literal[
    "GENERAL_CHAT",
    "KNOWLEDGE_QUERY",
    "SHIPMENT_QUERY",
    "DRAFT_UPDATE",
    "SENSITIVE_ACTION",
]

CONFIDENCE_THRESHOLD = 0.6
jieba.setLogLevel(ERROR)


class DraftCandidate(BaseModel):
    """模型可从用户原话提取的非敏感草稿字段，禁止生成数据库资源 ID。"""

    model_config = ConfigDict(extra="forbid")

    sender_address_label: str | None = Field(default=None, max_length=128)
    receiver_address_label: str | None = Field(default=None, max_length=128)
    origin_district_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    destination_district_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    actual_weight_grams: int | None = Field(default=None, gt=0)
    length_cm: int | None = Field(default=None, gt=0)
    width_cm: int | None = Field(default=None, gt=0)
    height_cm: int | None = Field(default=None, gt=0)
    declared_value_cents: int | None = Field(default=None, ge=0)


class UnderstandingResult(BaseModel):
    """意图识别的稳定结果，供 LangGraph 和业务模块消费。"""

    model_config = ConfigDict(extra="forbid")

    intents: list[IntentName] = Field(min_length=1, max_length=3)
    primary_intent: IntentName
    confidence: float = Field(ge=0, le=1)
    shipment_no: str | None = Field(default=None, pattern=r"^YT[A-Z0-9]{4,32}$")
    knowledge_query: str | None = Field(default=None, max_length=1000)
    draft: DraftCandidate = Field(default_factory=DraftCandidate)
    requires_confirmation: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)
    recognition_path: Literal["RULE", "LLM", "FALLBACK"] = "LLM"


@dataclass(frozen=True, slots=True)
class PreprocessedText:
    """保留规范化文本和分词结果，供规则匹配与追踪复用。"""

    original: str
    normalized: str
    tokens: tuple[str, ...]


# 这里只承担字符规范化，不承担意图判断；词表可被完整 OpenCC 适配器替换。
_TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {
        "臺": "台", "灣": "湾", "門": "门", "點": "点", "遞": "递",
        "貨": "货", "單": "单", "號": "号", "查": "查", "詢": "询",
        "軌": "轨", "跡": "迹", "預": "预", "計": "计", "達": "达",
        "費": "费", "規": "规", "則": "则", "賠": "赔", "償": "偿",
        "價": "价", "裝": "装", "確": "确", "認": "认", "創": "创",
        "建": "建", "異": "异", "常": "常", "處": "处", "理": "理",
        "運": "运",
    }
)
_WHITESPACE = re.compile(r"\s+")


def preprocess_text(value: str) -> PreprocessedText:
    """执行全半角、繁简、大小写、空白统一和中文分词。"""
    normalized = unicodedata.normalize("NFKC", value).translate(
        _TRADITIONAL_TO_SIMPLIFIED
    )
    normalized = _WHITESPACE.sub(" ", normalized).strip().lower()
    tokens = tuple(token.strip() for token in jieba.cut(normalized) if token.strip())
    return PreprocessedText(original=value, normalized=normalized, tokens=tokens)


@dataclass(frozen=True, slots=True)
class FastPathRule:
    """只描述高精度规则；出现多个候选时必须放弃快速路径。"""

    intent: IntentName
    patterns: tuple[re.Pattern[str], ...]


_FAST_PATH_RULES = (
    FastPathRule(
        "SHIPMENT_QUERY",
        (
            re.compile(r"(?:查|看|问).{0,8}(?:运单|快递|包裹).{0,8}(?:状态|进度|轨迹|到哪)"),
            re.compile(r"(?:运单|快递|包裹).{0,8}(?:到哪|进度|轨迹|预计.{0,2}到)"),
            re.compile(r"\byt[a-z0-9]{4,32}\b.{0,8}(?:查|状态|轨迹|到哪)"),
        ),
    ),
    FastPathRule(
        "KNOWLEDGE_QUERY",
        (
            re.compile(r"(?:禁寄|限寄|能不能寄|可以寄吗)"),
            re.compile(r"(?:包装|保价|赔付|赔偿).{0,8}(?:规则|要求|怎么|如何)"),
        ),
    ),
    FastPathRule(
        "DRAFT_UPDATE",
        (
            re.compile(r"(?:从|寄件地址).{1,30}(?:寄到|送到|收件地址)"),
            re.compile(r"(?:重量|重).{0,4}\d+(?:\.\d+)?\s*(?:克|公斤|千克|kg|g)"),
            re.compile(r"(?:尺寸|箱子).{0,8}\d+\s*[x×乘*]\s*\d+\s*[x×乘*]\s*\d+"),
        ),
    ),
    FastPathRule(
        "SENSITIVE_ACTION",
        (
            re.compile(r"(?:确认|立即|现在|帮我).{0,6}(?:下单|创建运单|支付|退款|取消运单)"),
            re.compile(r"(?:就按|按这个).{0,6}(?:下单|创建|支付)"),
        ),
    ),
)


def fast_path(
    preprocessed: PreprocessedText,
    address_labels: list[str],
) -> UnderstandingResult | None:
    """命中唯一高精度意图时返回；未命中或冲突时交给 LLM。"""
    matched = {
        rule.intent
        for rule in _FAST_PATH_RULES
        if any(pattern.search(preprocessed.normalized) for pattern in rule.patterns)
    }
    if len(matched) != 1:
        return None
    intent = matched.pop()
    shipment_match = re.search(r"\byt[a-z0-9]{4,32}\b", preprocessed.normalized)
    draft = _extract_fast_draft(preprocessed.normalized, address_labels)
    return UnderstandingResult(
        intents=[intent],
        primary_intent=intent,
        confidence=0.99,
        shipment_no=shipment_match.group(0).upper() if shipment_match else None,
        knowledge_query=(
            preprocessed.original if intent == "KNOWLEDGE_QUERY" else None
        ),
        draft=draft,
        requires_confirmation=intent == "SENSITIVE_ACTION",
        recognition_path="RULE",
    )


def _extract_fast_draft(normalized: str, address_labels: list[str]) -> DraftCandidate:
    """只提取格式明确的高频槽位，模糊内容留给 LLM Slow Path。"""
    values: dict[str, object] = {}
    weight = re.search(
        r"(?:(?:重量|重).{0,4})?(\d+(?:\.\d+)?)\s*(公斤|千克|kg|克|g)",
        normalized,
    )
    if weight:
        number = float(weight.group(1))
        values["actual_weight_grams"] = round(
            number * 1000 if weight.group(2) in {"公斤", "千克", "kg"} else number
        )
    dimensions = re.search(
        r"(?:尺寸|箱子)[^0-9]{0,8}(\d+)\s*[x×乘*]\s*(\d+)\s*[x×乘*]\s*(\d+)",
        normalized,
    )
    if dimensions:
        values.update(
            length_cm=int(dimensions.group(1)),
            width_cm=int(dimensions.group(2)),
            height_cm=int(dimensions.group(3)),
        )
    route = re.search(r"从(.{1,20}?)(?:寄到|送到)(.{1,20}?)(?:[，,。]|$)", normalized)
    if route:
        sender = _unique_label(route.group(1), address_labels)
        receiver = _unique_label(route.group(2), address_labels)
        if sender:
            values["sender_address_label"] = sender
        if receiver:
            values["receiver_address_label"] = receiver
    return DraftCandidate.model_validate(values)


def _unique_label(value: str, address_labels: list[str]) -> str | None:
    """只允许当前地址簿中唯一出现的完整标签进入规则槽位。"""
    matches = [label for label in address_labels if label.lower() == value.strip()]
    return matches[0] if len(matches) == 1 else None


UNDERSTANDING_PROMPT = """你是 Yitu 物流的意图识别器。调用 classify_logistics_intent 函数返回结果，不直接回答用户。
可选意图只有 GENERAL_CHAT、KNOWLEDGE_QUERY、SHIPMENT_QUERY、DRAFT_UPDATE、SENSITIVE_ACTION。
支持口语、同义表达、省略和多意图；primary_intent 表示当前最应该先处理的意图。
创建运单、确认下单、支付、退款、取消或其他改变业务状态的请求属于 SENSITIVE_ACTION，requires_confirmation 必须为 true。
物流规则、禁限寄、包装、赔付、保价和时效政策属于 KNOWLEDGE_QUERY。
本人运单状态、轨迹、费用或预计到达属于 SHIPMENT_QUERY。
提供或修改寄件地址、收件地址、重量、尺寸、声明价值属于 DRAFT_UPDATE。
地址只能原样提取为地址标签，禁止生成数据库 ID。重量换算为克，金额换算为分；未明确提供的字段必须为 null。
当前仅支持上门取件和送货上门，不提取网点寄件或网点自提字段。
不确定时降低 confidence 并给出一个具体 clarification_question。

示例：
用户：我的那个包裹走到哪一步了
结果：primary_intent=SHIPMENT_QUERY, confidence=0.95
用户：电脑寄出去要怎么包装才稳妥
结果：primary_intent=KNOWLEDGE_QUERY, confidence=0.94, knowledge_query=电脑寄件包装要求
用户：从公司寄到家，2.5公斤，箱子30乘20乘15
结果：primary_intent=DRAFT_UPDATE, confidence=0.97, draft.sender_address_label=公司, draft.receiver_address_label=家, draft.actual_weight_grams=2500
用户：帮我弄一下
结果：primary_intent=GENERAL_CHAT, confidence=0.3, clarification_question=你想查询运单、了解寄件规则，还是准备新的寄件信息？
"""


class UnderstandingService:
    """依次执行预处理、规则快速路径、LLM 路径和置信度降级。"""

    def __init__(self, model: ModelAdapter) -> None:
        self._model = model

    async def understand(
        self,
        history: list[ModelMessage],
        user_message: str,
        address_labels: list[str],
    ) -> UnderstandingResult:
        """返回统一的 `{intent, slots, confidence}` 结构供下游执行。"""
        preprocessed = preprocess_text(user_message)
        rule_result = fast_path(preprocessed, address_labels)
        if rule_result is not None:
            return rule_result

        messages = [ModelMessage(role="system", content=UNDERSTANDING_PROMPT)]
        if address_labels:
            labels = "、".join(address_labels[:50])
            messages.append(
                ModelMessage(
                    role="system",
                    content=f"当前用户可选的地址标签只有：{labels}。地址字段只能使用其中的完整标签。",
                )
            )
        messages.extend(history[-10:])
        if not messages or messages[-1].role != "user" or messages[-1].content != user_message:
            messages.append(ModelMessage(role="user", content=user_message))
        result = await self._model.complete_structured(messages, UnderstandingResult)
        result = result.model_copy(update={"recognition_path": "LLM"})
        if result.confidence >= CONFIDENCE_THRESHOLD:
            return result
        question = result.clarification_question or "你想查询运单、了解寄件规则，还是准备新的寄件信息？"
        return result.model_copy(
            update={
                "primary_intent": "GENERAL_CHAT",
                "clarification_question": question,
                "recognition_path": "FALLBACK",
            }
        )
