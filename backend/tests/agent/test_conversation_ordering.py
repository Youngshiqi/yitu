"""Agent 草稿持久化、缺失字段和共享创建命令契约。"""

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from yitu.agent.drafts import DraftPatch, DraftService
from yitu.agent.models import AgentConversation
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError
from yitu.pricing.schemas import QuoteView
from yitu.shipments.enums import DeliveryMethod, PickupMethod

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


async def test_draft_update_tracks_missing_fields_and_invalidates_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 12, 14, 0, tzinfo=TZ)
    actor, conversation_id = await _seed_conversation(now)

    async with SessionFactory() as session, session.begin():
        service = DraftService(session)
        draft = await service.update(
            conversation_id,
            actor,
            DraftPatch(
                pickup_method=PickupMethod.DOOR_PICKUP,
                delivery_method=DeliveryMethod.HOME_DELIVERY,
            ),
        )
        assert draft.status == "INCOMPLETE"
        assert "sender_address_id" in draft.missing_fields
        assert "receiver_address_id" in draft.missing_fields

        fake_quote = QuoteView(
            id=uuid4(),
            rule_version="v1",
            input_snapshot={},
            fee_items=[],
            volume_weight_grams=1000,
            billable_weight_grams=1000,
            total_cents=1800,
            created_at=now,
        )

        async def fake_validate(
            service_self: DraftService,
            cid: object,
            received_actor: object,
        ) -> object:
            del service_self, cid, received_actor
            from yitu.shipments.schemas import CreateShipmentCommand, ShipmentDraft

            return CreateShipmentCommand(
                draft=ShipmentDraft(
                    sender_address_id=uuid4(),
                    receiver_address_id=uuid4(),
                    pickup_method=PickupMethod.DOOR_PICKUP,
                    delivery_method=DeliveryMethod.HOME_DELIVERY,
                )
            )

        async def fake_quote_call(*args: object, **kwargs: object) -> QuoteView:
            del args, kwargs
            return fake_quote

        monkeypatch.setattr("yitu.agent.drafts.DraftService.validate", fake_validate)
        monkeypatch.setattr(
            "yitu.agent.drafts.PricingService.quote",
            fake_quote_call,
        )
        validated = await service.validate_and_quote(conversation_id, actor)
        assert validated.draft.quote_id == fake_quote.id
        assert validated.draft.status == "READY_FOR_CONFIRMATION"

        updated = await service.update(
            conversation_id,
            actor,
            DraftPatch(actual_weight_grams=2500),
        )
        assert updated.quote_id is None
        assert updated.quote_version is None


async def test_validate_rejects_other_users_address() -> None:
    now = datetime(2026, 8, 12, 14, 30, tzinfo=TZ)
    actor, conversation_id = await _seed_conversation(now)

    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        other = next(user for user in users if user.demo_key == "operations")
        draft = await DraftService(session).get_or_create(conversation_id, actor)
        draft.payload = {
            "sender_address_id": str(other.id),
            "receiver_address_id": str(other.id),
            "pickup_method": PickupMethod.DOOR_PICKUP.value,
            "delivery_method": DeliveryMethod.HOME_DELIVERY.value,
            "origin_district_code": "110101",
            "destination_district_code": "310101",
            "actual_weight_grams": 1000,
            "length_cm": 10,
            "width_cm": 10,
            "height_cm": 10,
        }
        draft.missing_fields = []

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as error:
            await DraftService(session).validate(conversation_id, actor)
        assert error.value.code in {"ADDRESS_NOT_FOUND", "FORBIDDEN_RESOURCE_OWNER"}


async def _seed_conversation(now: datetime) -> tuple[CurrentUser, UUID]:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        owner_row = next(user for user in users if user.demo_key == "customer")
        actor = CurrentUser(owner_row.id, Role.CUSTOMER, None)
        conversation = AgentConversation(
            owner_id=actor.id,
            title="草稿测试",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add(conversation)
        await session.flush()
        return actor, conversation.id
