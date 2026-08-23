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


def security_refusal(message: str) -> tuple[AgentIntent, str] | None:
    """只处理安全边界，不参与物流业务意图识别。"""
    if any(pattern.search(message) for pattern in INJECTION_PATTERNS):
        return "GENERAL_CHAT", INJECTION_REFUSAL
    if any(pattern.search(message) for pattern in CROSS_USER_PATTERNS):
        return "SHIPMENT_QUERY", CROSS_USER_REFUSAL
    return None

def classify_intent_node(state: AgentState) -> AgentState:
    """图的入口：先做超时守门，再执行安全拦截，最后把语义结果映射为有限路由。

    身份、历史等上下文由 service.py 在图外准备好塞进 state，本节点不加载
    任何业务上下文。主图是线性路由，只查超时防卡死；轮次/工具调用预算
    留给草稿子图的 _budget_refusal 防止 agentic loop 失控。
    """
    # 如果state里的router已经是blocked，直接返回空 dict
    if state.get("route") == "blocked":
        return {}

    # 超时检查
    timeout_refusal = _timeout_refusal(state)
    if timeout_refusal is not None:
        return _blocked_update(timeout_refusal)
    
    # 安全拦截
    # 取用户消息并strip()去除首尾空白
    message = state.get("user_message", "").strip()
    # 调用 security_refusal 做正则匹配
    refusal = security_refusal(message)
    if refusal is not None:
        return _classification(refusal[0], "BLOCKED", "blocked", refusal[1])
    
    
    intent = state.get("semantic_intent", "GENERAL_CHAT")
    if state.get("requires_confirmation") or intent == "SENSITIVE_ACTION":
        return _classification("SENSITIVE_ACTION", "WRITE_ACTION", "confirmation")
    
    # 意图路由映射表
    routes: dict[AgentIntent, tuple[AgentRisk, AgentRoute]] = {
        # LOW：无业务数据访问，闲聊/知识/运费
        "GENERAL_CHAT": ("LOW", "respond"),
        "KNOWLEDGE_QUERY": ("LOW", "knowledge"),
        "PRICING_QUERY": ("LOW", "pricing_rule"),
        # PERSONAL_DATA：涉及个人数据，运单/地址/身份，必须按 actor 身份查询
        "SHIPMENT_QUERY": ("PERSONAL_DATA", "read_tool"),
        "ADDRESS_QUERY": ("PERSONAL_DATA", "address_tool"),
        "IDENTITY_QUERY": ("PERSONAL_DATA", "identity_tool"),
        # WRITE_ACTION：涉及写操做，草稿/敏感动作，必须走确认边界
        "DRAFT_UPDATE": ("WRITE_ACTION", "draft"),
        "SENSITIVE_ACTION": ("WRITE_ACTION", "confirmation"),
    }
    risk, route = routes.get(intent, ("BLOCKED", "blocked"))
    return _classification(intent, risk, route)


def knowledge_node(state: AgentState) -> AgentState:
    """为 RAG 工具产出受控动作，不伪造知识证据。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "SEARCH_PUBLISHED_KNOWLEDGE",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查找已发布的物流规则。",
    }


def pricing_rule_node(state: AgentState) -> AgentState:
    """为运费规则查询工具产出动作，金额以确定性业务服务为准。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "QUERY_PRICING_RULES",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查询当前生效的运费规则。",
    }


def read_tool_node(state: AgentState) -> AgentState:
    """为任务三的本人业务查询工具产出动作，身份范围来自后端状态。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "QUERY_OWN_SHIPMENT",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查询当前账号下的运单信息。",
    }


def address_tool_node(state: AgentState) -> AgentState:
    """为本人地址簿查询工具产出动作，身份范围来自后端状态。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "QUERY_OWN_ADDRESSES",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查看当前账号下的地址簿。",
    }


def identity_tool_node(state: AgentState) -> AgentState:
    """为本人身份查询工具产出动作，身份范围来自后端状态。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "QUERY_OWN_IDENTITY",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你查看当前账号信息。",
    }


def draft_node(state: AgentState) -> AgentState:
    """把自然语言草稿变更送往后续确定性草稿服务。"""
    refusal = _timeout_refusal(state)
    if refusal is not None:
        return _blocked_update(refusal)
    return {
        "next_action": "UPDATE_SHIPMENT_DRAFT",
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "response": "好的，我来帮你整理寄件信息。接下来会由系统完成业务校验。",
    }


def confirmation_node(state: AgentState) -> AgentState:
    """敏感动作只能停在确认边界，当前节点绝不直接执行写操作。"""
    return {
        "next_action": "REQUEST_EXPLICIT_CONFIRMATION",
        "response": "没问题。这个操作需要你查看确认内容并明确同意后，我才能继续执行。",
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
        "pricing_rule",
        "read_tool",
        "draft",
        "confirmation",
        "blocked",
        "address_tool",
        "identity_tool",
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
    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", 4):
        return BUDGET_REFUSAL
    return None


def _timeout_refusal(state: AgentState) -> str | None:
    """主图专用：主图是线性路由，只防卡死，不查轮次/工具调用。

    主图单次线性执行、节点本身不调工具，turn_count/tool_call_count 永远不会
    超限；草稿子图才需要完整的 _budget_refusal 防止 agentic loop 失控。
    """
    started_at = state.get("execution_started_at", monotonic())
    timeout = state.get("timeout_seconds", 30.0)
    if timeout <= 0 or monotonic() - started_at > timeout:
        return TIMEOUT_REFUSAL
    return None


def _blocked_update(reason: str) -> AgentState:
    return {
        "risk": "BLOCKED",
        "route": "blocked",
        "refusal_reason": reason,
        "next_action": "REFUSE",
        "response": reason,
    }
