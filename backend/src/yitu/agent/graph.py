"""受控 LangGraph 工作流装配。"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from yitu.agent.nodes import (
    address_tool_node,
    blocked_node,
    classify_intent_node,
    confirmation_node,
    draft_node,
    identity_tool_node,
    knowledge_node,
    load_context_node,
    pricing_rule_node,
    read_tool_node,
    response_node,
    route_after_classification,
)
from yitu.agent.state import AgentState


def build_agent_graph() -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """构建只负责路由的图，业务工具和写操作由后续任务注入。"""
    graph = StateGraph(AgentState)
    graph.add_node("load_context", load_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("pricing_rule", pricing_rule_node)
    graph.add_node("read_tool", read_tool_node)
    graph.add_node("address_tool", address_tool_node)
    graph.add_node("identity_tool", identity_tool_node)
    graph.add_node("draft", draft_node)
    graph.add_node("confirmation", confirmation_node)
    graph.add_node("respond", response_node)
    graph.add_node("blocked", blocked_node)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classification,
        {
            "knowledge": "knowledge",
            "pricing_rule": "pricing_rule",
            "read_tool": "read_tool",
            "address_tool": "address_tool",
            "identity_tool": "identity_tool",
            "draft": "draft",
            "confirmation": "confirmation",
            "respond": "respond",
            "blocked": "blocked",
        },
    )
    for terminal_node in (
        "knowledge",
        "pricing_rule",
        "read_tool",
        "address_tool",
        "identity_tool",
        "draft",
        "confirmation",
        "respond",
        "blocked",
    ):
        graph.add_edge(terminal_node, END)
    return graph.compile()
