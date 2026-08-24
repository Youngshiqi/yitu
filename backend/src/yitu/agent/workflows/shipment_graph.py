"""八节点寄件子图装配。"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from yitu.agent.runtime.context import AgentRuntimeContext
from yitu.agent.workflow_nodes.shipment_nodes import (
    confirmation_route,
    create_confirmed_shipment_node,
    create_quote_node,
    creation_route,
    draft_action_route,
    draft_agent_node,
    draft_tools_node,
    draft_tools_route,
    load_draft_node,
    quote_route,
    request_confirmation_node,
    shipment_failure_node,
    validate_draft_node,
    validation_route,
)
from yitu.agent.workflow_state import ShipmentState


def build_shipment_graph(
    *, checkpointer: Any = None
) -> CompiledStateGraph[ShipmentState, AgentRuntimeContext, ShipmentState, ShipmentState]:
    graph = StateGraph(ShipmentState, context_schema=AgentRuntimeContext)
    graph.add_node("load_draft_node", load_draft_node)
    graph.add_node("draft_agent_node", draft_agent_node)
    graph.add_node("draft_tools_node", draft_tools_node)
    graph.add_node("validate_draft_node", validate_draft_node)
    graph.add_node("create_quote_node", create_quote_node)
    graph.add_node("request_confirmation_node", request_confirmation_node)
    graph.add_node("create_confirmed_shipment_node", create_confirmed_shipment_node)
    graph.add_node("shipment_failure_node", shipment_failure_node)

    graph.add_edge(START, "load_draft_node")
    graph.add_edge("load_draft_node", "draft_agent_node")
    graph.add_conditional_edges("draft_agent_node", draft_action_route)
    graph.add_conditional_edges("draft_tools_node", draft_tools_route)
    graph.add_conditional_edges("validate_draft_node", validation_route)
    graph.add_conditional_edges("create_quote_node", quote_route)
    graph.add_conditional_edges("request_confirmation_node", confirmation_route)
    graph.add_conditional_edges("create_confirmed_shipment_node", creation_route)
    graph.add_edge("shipment_failure_node", END)
    return graph.compile(checkpointer=checkpointer, name="yitu_shipment")
