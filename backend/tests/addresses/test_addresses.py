"""地址簿软删除：删除仅打 deleted_at 标记，物理行保留且不再参与列表/查重/读取。"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import (
    delete_address,
    find_matching_address,
    get_owned_address,
    list_addresses,
)
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError
from yitu.regions.models import AdministrativeRegion, RegionLevel

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_region_path(
    session: AsyncSession,
) -> tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion]:
    """幂等获取省/市/区三级区划（唯一约束按 level+code 复用已有行）。"""
    specs = (
        ("110000", "北京市", RegionLevel.PROVINCE),
        ("110000", "北京市", RegionLevel.CITY),
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


async def _seed_owner_and_address(
    session: AsyncSession,
) -> tuple[UUID, Address, AdministrativeRegion]:
    """创建 customer.demo 的一条正式地址，返回 owner_id、地址与所在区。"""
    users = await seed_demo_users(session)
    owner = next(user for user in users if user.demo_key == "customer")
    province, city, district = await _seed_region_path(session)
    # 电话随机生成：共享测试库存在历史残留地址，避免撞上相同五元组行
    phone = f"138{uuid4().int % 10**8:08d}"
    address = Address(
        owner_id=owner.id,
        recipient_name="张三",
        phone=phone,
        province_region_id=province.id,
        city_region_id=city.id,
        district_region_id=district.id,
        district_code="110105",
        detail="建国路88号",
        ephemeral=False,
    )
    session.add(address)
    await session.flush()
    return owner.id, address, district


async def test_delete_address_hides_from_list_but_keeps_row() -> None:
    """软删除后列表不再返回，但物理行保留且 deleted_at 非空。"""
    async with SessionFactory() as session, session.begin():
        owner_id, address, _ = await _seed_owner_and_address(session)
        actor = CurrentUser(owner_id, Role.CUSTOMER, None)

        await delete_address(session, address)
        await session.flush()

        listed = await list_addresses(session, actor)
        assert all(item.id != address.id for item in listed)

        row = await session.get(Address, address.id)
        assert row is not None
        assert row.deleted_at is not None
        assert row.ephemeral is False


async def test_find_matching_address_excludes_deleted() -> None:
    """软删除后同五元组不再命中，避免复用已删行。"""
    async with SessionFactory() as session, session.begin():
        owner_id, address, district = await _seed_owner_and_address(session)
        await delete_address(session, address)
        await session.flush()

        match = await find_matching_address(
            session, owner_id, "张三", address.phone, district.id, "建国路88号"
        )
        assert match is None


async def test_get_owned_address_deleted_raises_not_found() -> None:
    """读取已软删除地址应视为不存在，返回 404。"""
    async with SessionFactory() as session, session.begin():
        owner_id, address, _ = await _seed_owner_and_address(session)
        await delete_address(session, address)
        await session.flush()

        with pytest.raises(AppError) as exc_info:
            await get_owned_address(
                session, address.id, CurrentUser(owner_id, Role.CUSTOMER, None)
            )
        assert exc_info.value.code == "ADDRESS_NOT_FOUND"
