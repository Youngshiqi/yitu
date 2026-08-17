"""纯对话下单：确认词判定、确认改写与授权落库契约。"""

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.agent.drafts import DraftPatch, DraftService
from yitu.agent.models import (
    AgentActionGrant,
    AgentConversation,
    AgentShipmentDraft,
)
from yitu.agent.service import AgentConversationService
from yitu.agent.tools.drafts import execute_save_address
from yitu.agent.understanding import (
    UnderstandingResult,
    is_confirmation_word,
    is_save_address_word,
)
from yitu.demo.seed import seed_demo_pricing, seed_demo_users
from yitu.identity.models import Role, Station
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.database import SessionFactory
from yitu.regions.models import AdministrativeRegion, RegionLevel
from yitu.regions.service import resolve_region_by_names
from yitu.shipments.enums import ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.stations.models import ServiceArea

TZ = ZoneInfo("Asia/Shanghai")


def test_is_confirmation_word_matches() -> None:
    for word in (
        "确认", "确定", "下单", "确认下单", "好的", "好", "可以", "行",
        "没问题", "就这样", "同意", "嗯", "是的", "确认。", "好的！", "可以 ",
    ):
        assert is_confirmation_word(word), word


def test_is_confirmation_word_rejects_other() -> None:
    for word in (
        "好的，我再看看", "帮我查运单", "确认一下再说", "随便", "取消",
        "我不确认", "顺便下单",
    ):
        assert not is_confirmation_word(word), word


async def _seed_actor_and_conversation(session: AsyncSession) -> tuple[CurrentUser, UUID]:
    users = await seed_demo_users(session)
    owner = next(user for user in users if user.demo_key == "customer")
    actor = CurrentUser(owner.id, Role.CUSTOMER, None)
    conversation = AgentConversation(
        owner_id=actor.id,
        title="纯对话下单测试",
        status="ACTIVE",
        created_at=datetime(2026, 8, 17, tzinfo=TZ),
        updated_at=datetime(2026, 8, 17, tzinfo=TZ),
    )
    session.add(conversation)
    await session.flush()
    return actor, conversation.id


async def _seed_region_path(
    session: AsyncSession,
    *,
    province_code: str,
    province_name: str,
    city_code: str,
    city_name: str,
    district_code: str,
    district_name: str,
) -> tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion]:
    """幂等创建省/市/区三级区划（唯一约束按 level+code 复用已有行）。"""
    specs = (
        (province_code, province_name, RegionLevel.PROVINCE),
        (city_code, city_name, RegionLevel.CITY),
        (district_code, district_name, RegionLevel.DISTRICT),
    )
    regions: dict[RegionLevel, AdministrativeRegion] = {}
    for code, name, level in specs:
        region = await session.scalar(
            select(AdministrativeRegion).where(
                AdministrativeRegion.level == level,
                AdministrativeRegion.code == code,
            )
        )
        if region is None:
            region = AdministrativeRegion(
                code=code, name=name, level=level, enabled=True, data_version="test"
            )
            session.add(region)
        regions[level] = region
    await session.flush()
    province = regions[RegionLevel.PROVINCE]
    city = regions[RegionLevel.CITY]
    district = regions[RegionLevel.DISTRICT]
    city.parent_id = province.id
    district.parent_id = city.id
    await session.flush()
    return province, city, district


async def _seed_address(
    session: AsyncSession,
    actor: CurrentUser,
    region: tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion],
    district_code: str,
    name: str,
    *,
    ephemeral: bool = False,
) -> Address:
    province, city, district = region
    address = Address(
        owner_id=actor.id,
        recipient_name=name,
        phone=f"13{uuid4().int % 10**9:09d}",
        province_region_id=province.id,
        city_region_id=city.id,
        district_region_id=district.id,
        district_code=district_code,
        detail=f"{name}路1号",
        ephemeral=ephemeral,
    )
    session.add(address)
    await session.flush()
    return address


async def _seed_station(session: AsyncSession, district_code: str, code: str) -> Station:
    station = await session.scalar(select(Station).where(Station.code == code))
    if station is None:
        station = Station(
            code=code,
            name=f"测试网点-{code}",
            district_code=district_code,
            enabled=True,
        )
        session.add(station)
        await session.flush()
    return station


async def _seed_service_area(
    session: AsyncSession, district_code: str, service_type: str, station: Station
) -> None:
    existing = await session.scalar(
        select(ServiceArea).where(
            ServiceArea.district_code == district_code,
            ServiceArea.service_type == service_type,
        )
    )
    if existing is None:
        session.add(
            ServiceArea(
                district_code=district_code,
                service_type=service_type,
                station_id=station.id,
                version=1,
            )
        )
        await session.flush()


@pytest.mark.asyncio(loop_scope="session")
async def test_maybe_confirm_rewrites_when_ready() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        session.add(
            AgentShipmentDraft(
                conversation_id=conversation_id,
                owner_id=actor.id,
                payload={},
                revision=1,
                status="READY_FOR_CONFIRMATION",
                missing_fields=[],
                updated_at=Clock.now(),
            )
        )
        await session.flush()

        understanding = UnderstandingResult(
            intents=["GENERAL_CHAT"], primary_intent="GENERAL_CHAT", confidence=0.5
        )
        result = await AgentConversationService(session)._maybe_confirm(
            conversation_id, actor, "确认", understanding
        )

        assert result.primary_intent == "SENSITIVE_ACTION"
        assert result.requires_confirmation is True
        assert result.recognition_path == "RULE"


@pytest.mark.asyncio(loop_scope="session")
async def test_maybe_confirm_ignores_when_not_ready() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        understanding = UnderstandingResult(
            intents=["GENERAL_CHAT"], primary_intent="GENERAL_CHAT", confidence=0.5
        )
        result = await AgentConversationService(session)._maybe_confirm(
            conversation_id, actor, "确认", understanding
        )

        assert result.primary_intent == "GENERAL_CHAT"
        assert result.requires_confirmation is False


@pytest.mark.asyncio(loop_scope="session")
async def test_maybe_confirm_ignores_non_confirmation_word() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        session.add(
            AgentShipmentDraft(
                conversation_id=conversation_id,
                owner_id=actor.id,
                payload={},
                revision=1,
                status="READY_FOR_CONFIRMATION",
                missing_fields=[],
                updated_at=Clock.now(),
            )
        )
        await session.flush()

        understanding = UnderstandingResult(
            intents=["GENERAL_CHAT"], primary_intent="GENERAL_CHAT", confidence=0.5
        )
        result = await AgentConversationService(session)._maybe_confirm(
            conversation_id, actor, "好的，我再看看", understanding
        )

        assert result.primary_intent == "GENERAL_CHAT"


async def _seed_quoted_draft(
    session: AsyncSession,
    actor: CurrentUser,
    conversation_id: UUID,
    *,
    ephemeral: bool = False,
) -> None:
    await seed_demo_pricing(session)
    sender_region = await _seed_region_path(
        session,
        province_code="110000",
        province_name="北京市",
        city_code="110000",
        city_name="北京市",
        district_code="110105",
        district_name="朝阳区",
    )
    receiver_region = await _seed_region_path(
        session,
        province_code="310000",
        province_name="上海市",
        city_code="310000",
        city_name="上海市",
        district_code="310105",
        district_name="长宁区",
    )
    sender = await _seed_address(
        session, actor, sender_region, "110105", "寄件人", ephemeral=ephemeral
    )
    receiver = await _seed_address(
        session, actor, receiver_region, "310105", "收件人", ephemeral=ephemeral
    )
    sender_station = await _seed_station(session, "110105", "BJS-TEST")
    receiver_station = await _seed_station(session, "310105", "SHS-TEST")
    await _seed_service_area(session, "110105", "HOME_PICKUP", sender_station)
    await _seed_service_area(session, "310105", "HOME_DELIVERY", receiver_station)

    await DraftService(session).update(
        conversation_id,
        actor,
        DraftPatch(
            sender_address_id=sender.id,
            receiver_address_id=receiver.id,
            origin_district_code="110105",
            destination_district_code="310105",
            estimated_weight_grams=2000,
            estimated_length_cm=30,
            estimated_width_cm=20,
            estimated_height_cm=15,
            package_category="文件",
            package_description="合同",
        ),
    )
    await DraftService(session).validate_and_quote(conversation_id, actor)


@pytest.mark.asyncio(loop_scope="session")
async def test_confirm_shipment_creates_shipment_and_consumes_grant() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        await _seed_quoted_draft(session, actor, conversation_id)

        before_ids = set(
            (
                await session.scalars(
                    select(Shipment.id).where(Shipment.owner_id == actor.id)
                )
            ).all()
        )

        reply = await AgentConversationService(session)._confirm_shipment(
            conversation_id, actor, str(uuid4())
        )

        all_shipments = list(
            await session.scalars(select(Shipment).where(Shipment.owner_id == actor.id))
        )
        created = [s for s in all_shipments if s.id not in before_ids]
        assert len(created) == 1
        shipment = created[0]
        assert shipment.status == ShipmentStatus.PENDING_PAYMENT
        assert shipment.shipment_no in reply
        assert "待支付" in reply

        grant = await session.scalar(
            select(AgentActionGrant).where(
                AgentActionGrant.conversation_id == conversation_id
            )
        )
        assert grant is not None
        assert grant.consumed_at is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_confirm_shipment_refuses_when_not_quoted() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)

        before = list(
            await session.scalars(select(Shipment).where(Shipment.owner_id == actor.id))
        )

        reply = await AgentConversationService(session)._confirm_shipment(
            conversation_id, actor, str(uuid4())
        )

        assert "还没有可确认的报价" in reply
        after = list(
            await session.scalars(select(Shipment).where(Shipment.owner_id == actor.id))
        )
        assert len(after) == len(before)


def test_is_save_address_word_matches() -> None:
    for word in ("保存", "保存地址", "保存吧", "好的", "好，保存吧", "嗯", "可以"):
        assert is_save_address_word(word), word


def test_is_save_address_word_rejects_negative() -> None:
    for word in ("先不保存", "不保存", "不用保存", "我再想想", "取消", "算了"):
        assert not is_save_address_word(word), word


@pytest.mark.asyncio(loop_scope="session")
async def test_resolve_region_by_names_matches() -> None:
    async with SessionFactory() as session, session.begin():
        province, city, district = await _seed_region_path(
            session,
            province_code="110000",
            province_name="北京市",
            city_code="110000",
            city_name="北京市",
            district_code="110105",
            district_name="朝阳区",
        )
        resolved = await resolve_region_by_names(session, "北京市", "北京市", "朝阳区")
        assert resolved[0].id == province.id
        assert resolved[1].id == city.id
        assert resolved[2].id == district.id

        # 去后缀也能命中
        resolved_short = await resolve_region_by_names(session, "北京", "北京", "朝阳")
        assert resolved_short[0].id == province.id
        assert resolved_short[1].id == city.id
        assert resolved_short[2].id == district.id


@pytest.mark.asyncio(loop_scope="session")
async def test_execute_save_address_creates_ephemeral_and_backfills() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        await _seed_region_path(
            session,
            province_code="110000",
            province_name="北京市",
            city_code="110000",
            city_name="北京市",
            district_code="110105",
            district_name="朝阳区",
        )
        before_ids = set(
            (
                await session.scalars(
                    select(Address.id).where(Address.owner_id == actor.id)
                )
            ).all()
        )

        result = await execute_save_address(
            session,
            actor,
            conversation_id,
            {
                "role": "sender",
                "recipient_name": "张三",
                "phone": f"138{uuid4().int % 10**8:08d}",
                "province_name": "北京市",
                "city_name": "北京市",
                "district_name": "朝阳区",
                "detail": "望京SOHO T1",
            },
        )

        assert "寄件地址" in result
        all_addresses = list(
            await session.scalars(select(Address).where(Address.owner_id == actor.id))
        )
        created = [a for a in all_addresses if a.id not in before_ids]
        assert len(created) == 1
        assert created[0].ephemeral is True
        assert created[0].district_code == "110105"
        draft = await DraftService(session).get_or_create(conversation_id, actor)
        assert draft.payload["sender_address_id"] == str(created[0].id)
        assert draft.payload["origin_district_code"] == "110105"


@pytest.mark.asyncio(loop_scope="session")
async def test_confirm_shipment_prompts_save_for_ephemeral_address() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        await _seed_quoted_draft(session, actor, conversation_id, ephemeral=True)

        reply = await AgentConversationService(session)._confirm_shipment(
            conversation_id, actor, str(uuid4())
        )

        assert "保存" in reply
        draft = await DraftService(session).get_or_create(conversation_id, actor)
        assert draft.status == "SHIPMENT_CREATED"
        pending = cast(
            list[str], draft.payload.get("pending_save_address_ids") or []
        )
        assert len(pending) == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_maybe_save_address_promotes_ephemeral() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        await _seed_quoted_draft(session, actor, conversation_id, ephemeral=True)
        await AgentConversationService(session)._confirm_shipment(
            conversation_id, actor, str(uuid4())
        )
        draft = await DraftService(session).get_or_create(conversation_id, actor)
        pending = cast(
            list[str], draft.payload.get("pending_save_address_ids") or []
        )
        assert pending

        understanding = UnderstandingResult(
            intents=["GENERAL_CHAT"], primary_intent="GENERAL_CHAT", confidence=0.5
        )
        result = await AgentConversationService(session)._maybe_save_address(
            conversation_id, actor, "保存", understanding
        )

        assert result.primary_intent == "GENERAL_CHAT"
        assert result.clarification_question is not None
        assert "已保存" in result.clarification_question

        draft = await DraftService(session).get_or_create(conversation_id, actor)
        assert draft.payload.get("pending_save_address_ids") == []
        for address_id in pending:
            address = await session.get(Address, UUID(str(address_id)))
            assert address is not None
            assert address.ephemeral is False
