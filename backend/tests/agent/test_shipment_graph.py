"""八节点寄件子图、草稿循环和人工确认测试。"""

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from tests.agent.fakes import (
    FakeAssistantReadPort,
    FakeConversationPort,
    FakeKnowledgePort,
    FakeShipmentWorkflowPort,
    FakeTracePort,
    ScriptedModelPort,
)
from yitu.agent.model_adapter import ToolCall, ToolCallResult
from yitu.agent.runtime.context import AgentRuntimeContext
from yitu.agent.workflow_state import (
    ConfirmationSnapshot,
    DraftProgress,
    KnowledgeEvidence,
    QuoteProgress,
    ShipmentReceipt,
)
from yitu.agent.workflows.assistant_graph import build_assistant_graph
from yitu.agent.workflows.shipment_graph import build_shipment_graph


def _context(
    model: ScriptedModelPort,
    shipment: FakeShipmentWorkflowPort,
) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        actor_id=uuid4(),
        request_id="request-1",
        model=model,
        knowledge=FakeKnowledgePort(
            KnowledgeEvidence(found=False, citations=[], message="无")
        ),
        assistant_reads=FakeAssistantReadPort(),
        shipment=shipment,
        conversation=FakeConversationPort(),
        trace=FakeTracePort(),
    )


async def test_draft_agent_executes_tool_then_observes_progress() -> None:
    model = ScriptedModelPort(
        [
            ToolCallResult(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="draft-1",
                        name="update_draft",
                        arguments={"estimated_weight_grams": 3000},
                    ),
                ),
            ),
            ToolCallResult(content="还需要收件地址。", tool_calls=()),
        ]
    )
    shipment = FakeShipmentWorkflowPort(
        DraftProgress(
            status="INCOMPLETE",
            revision=1,
            missing_fields=["receiver_address_id"],
        )
    )
    graph = build_shipment_graph()

    result = await graph.ainvoke(
        {
            "conversation_id": str(uuid4()),
            "handoff": {
                "user_message": "三公斤衣服",
                "extracted_fields": {},
            },
        },
        context=_context(model, shipment),
    )

    assert result["workflow_result"]["status"] == "NEEDS_INPUT"
    assert result["workflow_result"]["response"] == "还需要收件地址。"
    assert len(shipment.draft_calls) == 1
    assert [item["role"] for item in result["messages"]][-2:] == [
        "tool",
        "assistant",
    ]


def test_shipment_graph_has_exactly_eight_named_nodes() -> None:
    graph = build_shipment_graph()

    assert set(graph.nodes) == {
        "__start__",
        "load_draft_node",
        "draft_agent_node",
        "draft_tools_node",
        "validate_draft_node",
        "create_quote_node",
        "request_confirmation_node",
        "create_confirmed_shipment_node",
        "shipment_failure_node",
    }


async def test_confirm_resume_creates_shipment_only_after_interrupt() -> None:
    conversation_id = uuid4()
    quote_id = uuid4()
    model = ScriptedModelPort(
        [ToolCallResult(content="信息已齐全。", tool_calls=())]
    )
    shipment = FakeShipmentWorkflowPort(
        DraftProgress(status="READY_FOR_QUOTE", revision=2, missing_fields=[]),
        quote=QuoteProgress(
            quote_id=quote_id,
            quote_version="v1",
            draft_revision=2,
            total_cents=1800,
        ),
        confirmation=ConfirmationSnapshot(
            conversation_id=conversation_id,
            draft_revision=2,
            quote_id=quote_id,
            quote_version="v1",
            total_cents=1800,
            summary="三公斤衣服",
        ),
        receipt=ShipmentReceipt(
            shipment_id=uuid4(),
            shipment_no="YT202608240001",
            total_cents=1800,
        ),
    )
    context = _context(model, shipment)
    graph = build_shipment_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "shipment-test"}}

    paused = await graph.ainvoke(
        {
            "conversation_id": str(conversation_id),
            "handoff": {
                "user_message": "寄出这些衣服",
                "extracted_fields": {},
            },
        },
        config,
        context=context,
    )

    assert paused["__interrupt__"]
    assert shipment.create_requests == []

    completed = await graph.ainvoke(
        Command(resume="confirm"),
        config,
        context=context,
    )

    assert completed["workflow_result"]["status"] == "CREATED"
    assert completed["workflow_result"]["receipt"]["shipment_no"] == "YT202608240001"
    assert shipment.create_requests == ["request-1"]


async def test_parent_checkpointer_resumes_child_interrupt() -> None:
    conversation_id = uuid4()
    quote_id = uuid4()
    model = ScriptedModelPort(
        [
            ToolCallResult(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="handoff-1",
                        name="start_shipment",
                        arguments={"extracted_fields": {}},
                    ),
                ),
            ),
            ToolCallResult(content="信息已齐全。", tool_calls=()),
        ]
    )
    shipment = FakeShipmentWorkflowPort(
        DraftProgress(status="READY_FOR_QUOTE", revision=3, missing_fields=[]),
        quote=QuoteProgress(
            quote_id=quote_id,
            quote_version="v2",
            draft_revision=3,
            total_cents=2200,
        ),
        confirmation=ConfirmationSnapshot(
            conversation_id=conversation_id,
            draft_revision=3,
            quote_id=quote_id,
            quote_version="v2",
            total_cents=2200,
            summary="文件",
        ),
        receipt=ShipmentReceipt(
            shipment_id=uuid4(),
            shipment_no="YT202608240002",
            total_cents=2200,
        ),
    )
    context = _context(model, shipment)
    child = build_shipment_graph()
    parent = build_assistant_graph(child, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "parent-child-test"}}

    paused = await parent.ainvoke(
        {
            "conversation_id": str(conversation_id),
            "user_message": "帮我寄文件",
        },
        config,
        context=context,
    )

    assert paused["__interrupt__"]
    assert shipment.create_requests == []

    completed = await parent.ainvoke(
        Command(resume="confirm"),
        config,
        context=context,
    )

    assert completed["shipment_result"]["status"] == "CREATED"
    assert completed["response"].startswith("运单 YT202608240002 已创建")
