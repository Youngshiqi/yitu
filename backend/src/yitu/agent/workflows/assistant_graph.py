"""七节点助手主图装配。"""

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from yitu.agent.runtime.context import AgentRuntimeContext
from yitu.agent.workflow_nodes.assistant_nodes import (
    assistant_action_route,
    assistant_agent_node,
    assistant_tools_node,
    assistant_tools_route,
)
from yitu.agent.workflow_nodes.context_nodes import (
    load_context_node,
    security_gate_node,
    security_result_route,
)
from yitu.agent.workflow_nodes.finalize_nodes import (
    finalize_turn_node,
    handle_failure_node,
    shipment_result_route,
    shipment_workflow_node,
)
from yitu.agent.workflow_state import AssistantState


def build_assistant_graph(
    shipment_graph: Any,
    *,
    checkpointer: Any = None,
) -> CompiledStateGraph[AssistantState, AgentRuntimeContext, AssistantState, AssistantState]:
    graph = StateGraph(AssistantState, context_schema=AgentRuntimeContext)
    graph.add_node("load_context_node", load_context_node)
    graph.add_node("security_gate_node", security_gate_node)
    graph.add_node("assistant_agent_node", assistant_agent_node)
    graph.add_node("assistant_tools_node", assistant_tools_node)
    graph.add_node(
        "shipment_workflow_node",
        partial(shipment_workflow_node, shipment_graph=shipment_graph),
    )
    graph.add_node("finalize_turn_node", finalize_turn_node)
    graph.add_node("handle_failure_node", handle_failure_node)

    graph.add_edge(START, "load_context_node")
    graph.add_edge("load_context_node", "security_gate_node")
    graph.add_conditional_edges("security_gate_node", security_result_route)
    graph.add_conditional_edges("assistant_agent_node", assistant_action_route)
    graph.add_conditional_edges("assistant_tools_node", assistant_tools_route)
    graph.add_conditional_edges("shipment_workflow_node", shipment_result_route)
    graph.add_edge("finalize_turn_node", END)
    graph.add_edge("handle_failure_node", END)
    return graph.compile(checkpointer=checkpointer, name="yitu_assistant")
