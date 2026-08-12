"""LangGraph 节点和确定性安全路由。"""

import re
from time import monotonic

from yitu.agent.prompts import (
    BUDGET_REFUSAL,
    CROSS_USER_REFUSAL,
    INJECTION_REFUSAL,
    TIMEOUT_REFUSAL,
)
from yitu.agent.state import AgentIntent, AgentRisk, AgentRoute, AgentState

INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则|提示词)"),
    re.compile(
        r"(显示|泄露|输出|show|reveal|print).{0,16}(系统提示词|system prompt)",
        re.IGNORECASE,
    ),
    re.compile(r"(绕过|取消|禁用).{0,8}(权限|安全|授权|审核)"),
    re.compile(r"you are now|developer message", re.IGNORECASE),
)
CROSS_USER_PATTERNS = (
    re.compile(r"(其他|别人|别人的|任意|全部)(客户|用户)?.{0,8}运单"),
    re.compile(r"查询.{0,8}(其他|别人|任意)(客户|用户)"),
)
SENSITIVE_ACTION_WORDS = (
    "创建运单",
    "确认下单",
    "支付",
    "退款",
    "取消运单",
    "重新派送",
    "再次派送",
    "创建异常工单",
    "处理异常",
)
DRAFT_WORDS = (
    "寄件",
    "收件",
    "地址",
    "重量",
    "尺寸",
    "物品",
    "服务方式",
    "修改草稿",
    "更新草稿",
    "报价",
)
KNOWLEDGE_WORDS = (
    "规则",
    "规定",
    "禁寄",
    "限寄",
    "包装",
    "赔付",
    "保价",
    "时效政策",
    "为什么",
)
SHIPMENT_QUERY_WORDS = (
    "我的运单",
    "我的快递",
    "查件",
    "物流轨迹",
    "到哪了",
    "预计到达",
    "运单费用",
)


def load_context_node(state: AgentState) -> AgentState:
    """校验执行预算并标记身份、历史和工作上下文已加载。"""
    refusal = _budget_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "context_loaded": True,
        "turn_count": state.get("turn_count", 0) + 1,
        "tool_call_count": state.get("tool_call_count", 0),
    }


def classify_intent_node(state: AgentState) -> AgentState:
    """使用确定性规则识别意图和风险，模型不能覆盖安全分类。"""
    if state.get("route") == "blocked":
        return {}
    message = state.get("user_message", "").strip()
    if any(pattern.search(message) for pattern in INJECTION_PATTERNS):
        return _classification("GENERAL_CHAT", "BLOCKED", "blocked", INJECTION_REFUSAL)
    if any(pattern.search(message) for pattern in CROSS_USER_PATTERNS):
        return _classification(
            "SHIPMENT_QUERY",
            "BLOCKED",
            "blocked",
            CROSS_USER_REFUSAL,
        )
    if any(word in message for word in SENSITIVE_ACTION_WORDS):
        return _classification("SENSITIVE_ACTION", "WRITE_ACTION", "confirmation")
    if any(word in message for word in SHIPMENT_QUERY_WORDS):
        return _classification("SHIPMENT_QUERY", "PERSONAL_DATA", "read_tool")
    if any(word in message for word in KNOWLEDGE_WORDS):
        return _classification("KNOWLEDGE_QUERY", "LOW", "knowledge")
    if any(word in message for word in DRAFT_WORDS):
        return _classification("DRAFT_UPDATE", "WRITE_ACTION", "draft")
    return _classification("GENERAL_CHAT", "LOW", "respond")


def knowledge_node(state: AgentState) -> AgentState:
    """为任务三的 RAG 工具产出受控动作，不伪造知识证据。"""
    refusal = _tool_budget_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "SEARCH_PUBLISHED_KNOWLEDGE",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "正在检索已发布的物流知识证据。",
    }


def read_tool_node(state: AgentState) -> AgentState:
    """为任务三的本人业务查询工具产出动作，身份范围来自后端状态。"""
    refusal = _tool_budget_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "QUERY_OWN_SHIPMENT",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "正在查询当前登录用户有权访问的运单信息。",
    }


def draft_node(state: AgentState) -> AgentState:
    """把自然语言草稿变更送往后续确定性草稿服务。"""
    refusal = _tool_budget_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "UPDATE_SHIPMENT_DRAFT",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "正在整理运单草稿字段，业务校验将在后端完成。",
    }


def confirmation_node(state: AgentState) -> AgentState:
    """敏感动作只能停在确认边界，当前节点绝不直接执行写操作。"""
    return {
        "next_action": "REQUEST_EXPLICIT_CONFIRMATION",
        "response": "该操作需要展示结构化确认内容，并由你明确确认后才能执行。",
    }


def response_node(state: AgentState) -> AgentState:
    """普通对话进入模型回复阶段，不调用业务工具。"""
    return {
        "next_action": "GENERATE_RESPONSE",
        "response": "请求已通过安全路由，可以生成普通回复。",
    }


def blocked_node(state: AgentState) -> AgentState:
    """统一输出安全拒绝，不向模型暴露内部匹配规则。"""
    return {
        "next_action": "REFUSE",
        "response": state.get("refusal_reason") or "请求已被安全策略拒绝。",
    }


def route_after_classification(state: AgentState) -> AgentRoute:
    """只读取确定性分类结果，未知值一律进入拒绝分支。"""
    route = state.get("route", "blocked")
    if route in {
        "respond",
        "knowledge",
        "read_tool",
        "draft",
        "confirmation",
        "blocked",
    }:
        return route
    return "blocked"


def _classification(
    intent: AgentIntent,
    risk: AgentRisk,
    route: AgentRoute,
    refusal_reason: str | None = None,
) -> AgentState:
    return {
        "intent": intent,
        "risk": risk,
        "route": route,
        "refusal_reason": refusal_reason,
    }


def _budget_refusal(state: AgentState) -> str | None:
    started_at = state.get("execution_started_at", monotonic())
    timeout = state.get("timeout_seconds", 30.0)
    if timeout <= 0 or monotonic() - started_at > timeout:
        return TIMEOUT_REFUSAL
    if state.get("turn_count", 0) >= state.get("max_turns", 8):
        return BUDGET_REFUSAL
    return None


def _tool_budget_refusal(state: AgentState) -> str | None:
    refusal = _budget_refusal(state)
    if refusal is not None:
        return refusal
    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", 4):
        return BUDGET_REFUSAL
    return None


def _blocked_update(reason: str) -> AgentState:
    return {
        "risk": "BLOCKED",
        "route": "blocked",
        "refusal_reason": reason,
        "next_action": "REFUSE",
        "response": reason,
    }
