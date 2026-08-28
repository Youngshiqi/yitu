"""单主图装配：单轮 Agent 与受控寄件事务共享同一张图。"""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from yitu.agent.runtime.graph_context import AgentRuntimeContext
from yitu.agent.workflow.nodes.agent_nodes import (
    assistant_agent_node,
    assistant_tools_node,
)
from yitu.agent.workflow.nodes.context_nodes import (
    load_context_node,
    security_gate_node,
)
from yitu.agent.workflow.nodes.final_nodes import (
    finalize_turn_node,
    handle_failure_node,
)
from yitu.agent.workflow.nodes.shipment_nodes import (
    create_quote_node,
    create_shipment_node,
    shipment_confirmation_node,
    shipment_process_node,
)
from yitu.agent.workflow.routes import (
    assistant_action_route,
    assistant_tools_route,
    confirmation_route,
    creation_route,
    quote_route,
    security_result_route,
    shipment_progress_route,
)
from yitu.agent.workflow.state import AssistantState


def build_assistant_graph(
    *, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[
    AssistantState, AgentRuntimeContext, AssistantState, AssistantState
]:
    """构建唯一的助手主图，所有寄件流转都由本图条件边决定。"""
    graph = StateGraph[AssistantState, AgentRuntimeContext, AssistantState, AssistantState](AssistantState, context_schema=AgentRuntimeContext)
    graph.add_node("load_context_node", load_context_node)
    graph.add_node("security_gate_node", security_gate_node)
    graph.add_node("assistant_agent_node", assistant_agent_node)
    graph.add_node("assistant_tools_node", assistant_tools_node)
    graph.add_node("shipment_process_node", shipment_process_node)
    graph.add_node("create_quote_node", create_quote_node)
    graph.add_node("shipment_confirmation_node", shipment_confirmation_node)
    graph.add_node("create_shipment_node", create_shipment_node)
    graph.add_node("finalize_turn_node", finalize_turn_node)
    graph.add_node("handle_failure_node", handle_failure_node)

    graph.add_edge(START, "load_context_node")
    graph.add_edge("load_context_node", "security_gate_node")
    graph.add_conditional_edges("security_gate_node", security_result_route)
    graph.add_conditional_edges("assistant_agent_node", assistant_action_route)
    graph.add_conditional_edges("assistant_tools_node", assistant_tools_route)
    graph.add_conditional_edges("shipment_process_node", shipment_progress_route)
    graph.add_conditional_edges("create_quote_node", quote_route)
    graph.add_conditional_edges("shipment_confirmation_node", confirmation_route)
    graph.add_conditional_edges("create_shipment_node", creation_route)
    graph.add_edge("finalize_turn_node", END)
    graph.add_edge("handle_failure_node", END)
    return graph.compile(checkpointer=checkpointer, name="yitu_assistant")
