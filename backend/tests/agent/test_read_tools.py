"""Agent 只读工具的身份范围、最小字段和引用契约。"""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from yitu.agent.tools.base import ToolContext
from yitu.agent.tools.identity import AddressBookTool, IdentityTool
from yitu.agent.tools.knowledge import KnowledgeSearchInput, KnowledgeSearchTool
from yitu.agent.tools.shipments import ShipmentReadInput, ShipmentReadTool
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.knowledge.retrieval import Evidence
from yitu.shipments.enums import ShipmentStatus
from yitu.shipments.service import ShipmentReadView, ShipmentView
from yitu.tracking.schemas import TrackingEventView

TZ = ZoneInfo("Asia/Shanghai")


def test_tool_inputs_reject_identity_override_and_extra_fields() -> None:
    """模型不能在工具输入中伪造 user_id 或扩大结果数量。"""
    with pytest.raises(ValidationError):
        ShipmentReadInput.model_validate(
            {"shipment_no": "YT12345678", "user_id": str(uuid4())}
        )
    with pytest.raises(ValidationError):
        KnowledgeSearchInput(query="禁寄规则", limit=6)


@pytest.mark.asyncio
async def test_identity_and_address_tools_only_return_minimum_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = CurrentUser(uuid4(), Role.CUSTOMER, None)
    address_id = uuid4()

    async def fake_list_addresses(session: object, user: CurrentUser) -> list[object]:
        del session
        assert user == actor
        return [
            SimpleNamespace(
                id=address_id,
                label="公司",
                district_code="110101",
                phone="13800000000",
                detail="不应进入模型的详细地址",
            )
        ]

    monkeypatch.setattr(
        "yitu.agent.tools.identity.list_addresses",
        fake_list_addresses,
    )
    context = ToolContext(actor=actor, session=SimpleNamespace())  # type: ignore[arg-type]
    identity = await IdentityTool().execute(context)
    addresses = await AddressBookTool().execute(context)

    assert identity.data is not None and identity.data.user_id == actor.id
    serialized = addresses.model_dump(mode="json")
    assert serialized["data"]["items"] == [
        {"id": str(address_id), "label": "公司", "district_code": "110101"}
    ]
    assert "phone" not in str(serialized)
    assert "详细地址" not in str(serialized)


@pytest.mark.asyncio
async def test_shipment_tool_uses_actor_scoped_application_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = CurrentUser(uuid4(), Role.CUSTOMER, None)
    shipment_id = uuid4()
    occurred_at = datetime(2026, 8, 12, 10, 0, tzinfo=TZ)

    async def fake_get_read_view(
        service: object,
        received_actor: CurrentUser,
        *,
        shipment_no: str | None = None,
    ) -> ShipmentReadView:
        del service
        assert received_actor == actor
        assert shipment_no == "YT12345678"
        return ShipmentReadView(
            shipment=ShipmentView(
                id=shipment_id,
                shipment_no="YT12345678",
                owner_id=actor.id,
                status=ShipmentStatus.IN_LINEHAUL,
            ),
            tracking=[
                TrackingEventView(
                    id=uuid4(),
                    sequence_no=1,
                    event_type="pickup",
                    message="已揽收",
                    visible_to_customer=True,
                    occurred_at=occurred_at,
                )
            ],
            paid_total_cents=1800,
            eta_at=occurred_at,
            promised_delivery_at=occurred_at,
        )

    monkeypatch.setattr(
        "yitu.shipments.service.ShipmentApplicationService.get_read_view",
        fake_get_read_view,
    )
    context = ToolContext(actor=actor, session=SimpleNamespace())  # type: ignore[arg-type]
    result = await ShipmentReadTool().execute(
        ShipmentReadInput(shipment_no="YT12345678"), context
    )

    assert result.found is True
    assert result.data is not None
    assert result.data.shipment_no == "YT12345678"
    assert result.data.paid_total_cents == 1800
    serialized = result.model_dump(mode="json")
    assert "owner_id" not in serialized["data"]
    assert "address" not in str(serialized).lower()


@pytest.mark.asyncio
async def test_knowledge_tool_preserves_citations_and_handles_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    responses = iter(
        [
            [
                Evidence(
                    document_id=document_id,
                    filename="禁寄规则.pdf",
                    category="prohibited-items",
                    index_version=3,
                    title="禁寄物品",
                    section_path=["第一章"],
                    content_type="paragraph",
                    page_start=None,
                    page_end=None,
                    content="禁止寄递危险品。",
                    score=0.91,
                )
            ],
            [],
        ]
    )

    async def fake_search(
        retriever: object,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[Evidence]:
        del retriever
        assert query == "禁寄规则"
        assert category is None
        assert limit == 5
        return next(responses)

    monkeypatch.setattr(
        "yitu.knowledge.retrieval.KnowledgeRetriever.search",
        fake_search,
    )
    context = ToolContext(
        actor=CurrentUser(uuid4(), Role.CUSTOMER, None),
        session=SimpleNamespace(),  # type: ignore[arg-type]
    )
    tool = KnowledgeSearchTool()
    found = await tool.execute(KnowledgeSearchInput(query="禁寄规则"), context)
    missing = await tool.execute(KnowledgeSearchInput(query="禁寄规则"), context)

    assert found.data is not None
    assert found.data.citations[0].document_id == document_id
    assert found.data.citations[0].score == 0.91
    assert missing.found is False
    assert missing.data is not None and missing.data.citations == []
