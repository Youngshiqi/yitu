"""草稿对话：地址簿外新地址的保存端点与临时地址过滤契约。"""

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import list_addresses
from yitu.agent.models import AgentConversation
from yitu.agent.schemas import DraftAddressCreate
from yitu.agent.service import AgentConversationService
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory
from yitu.regions.models import AdministrativeRegion, RegionLevel

pytestmark = pytest.mark.asyncio(loop_scope="session")
TZ = ZoneInfo("Asia/Shanghai")


async def _seed_actor_and_conversation(session: AsyncSession) -> tuple[CurrentUser, UUID]:
    users = await seed_demo_users(session)
    owner_row = next(user for user in users if user.demo_key == "customer")
    actor = CurrentUser(owner_row.id, Role.CUSTOMER, None)
    conversation = AgentConversation(
        owner_id=actor.id,
        title="地址保存测试",
        status="ACTIVE",
        created_at=datetime(2026, 8, 17, tzinfo=TZ),
        updated_at=datetime(2026, 8, 17, tzinfo=TZ),
    )
    session.add(conversation)
    await session.flush()
    return actor, conversation.id


async def _seed_region_path(
    session: AsyncSession,
) -> tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion]:
    """幂等创建省/市/区三级区划（唯一约束按 level+code 复用已有行）。"""
    specs = (
        ("110000", "北京市", RegionLevel.PROVINCE),
        ("110100", "北京市", RegionLevel.CITY),
        ("110105", "朝阳区", RegionLevel.DISTRICT),
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


def _payload(
    province: AdministrativeRegion,
    city: AdministrativeRegion,
    district: AdministrativeRegion,
    *,
    role: Literal["sender", "receiver"],
    save: bool,
) -> DraftAddressCreate:
    return DraftAddressCreate(
        role=role,
        save=save,
        label="家",
        recipient_name="张三",
        phone="13800138000",
        province_region_id=province.id,
        city_region_id=city.id,
        district_region_id=district.id,
        detail="建国路88号",
    )


async def test_save_draft_address_saves_formal_and_fills_receiver() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        province, city, district = await _seed_region_path(session)

        draft = await AgentConversationService(session).save_draft_address(
            conversation_id,
            actor,
            _payload(province, city, district, role="receiver", save=True),
        )

        receiver_id = draft.payload["receiver_address_id"]
        assert draft.payload["destination_district_code"] == "110105"
        assert "sender_address_id" in draft.missing_fields
        address = await session.get(Address, UUID(str(receiver_id)))
        assert address is not None and address.ephemeral is False
        listed = await list_addresses(session, actor)
        assert any(a.id == address.id for a in listed)


async def test_save_draft_address_ephemeral_not_listed() -> None:
    async with SessionFactory() as session, session.begin():
        actor, conversation_id = await _seed_actor_and_conversation(session)
        province, city, district = await _seed_region_path(session)

        draft = await AgentConversationService(session).save_draft_address(
            conversation_id,
            actor,
            _payload(province, city, district, role="sender", save=False),
        )

        sender_id = draft.payload["sender_address_id"]
        assert draft.payload["origin_district_code"] == "110105"
        address = await session.get(Address, UUID(str(sender_id)))
        assert address is not None and address.ephemeral is True
        listed = await list_addresses(session, actor)
        assert all(a.id != address.id for a in listed)


async def test_list_addresses_filters_ephemeral() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        owner = next(user for user in users if user.demo_key == "customer")
        province, city, district = await _seed_region_path(session)
        formal = Address(
            owner_id=owner.id,
            recipient_name="张三",
            phone="13800138000",
            province_region_id=province.id,
            city_region_id=city.id,
            district_region_id=district.id,
            district_code="110105",
            detail="建国路88号",
            ephemeral=False,
        )
        temporary = Address(
            owner_id=owner.id,
            recipient_name="李四",
            phone="13900139000",
            province_region_id=province.id,
            city_region_id=city.id,
            district_region_id=district.id,
            district_code="110105",
            detail="临时地址",
            ephemeral=True,
        )
        session.add_all([formal, temporary])
        await session.flush()

        listed = await list_addresses(
            session, CurrentUser(owner.id, Role.CUSTOMER, None)
        )

        ids = {address.id for address in listed}
        assert formal.id in ids
        assert temporary.id not in ids
