from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from yitu.addresses.models import Address
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError
from yitu.regions.service import resolve_region_path


async def get_owned_address(session: AsyncSession, address_id: UUID, user: CurrentUser) -> Address:
    address = await session.scalar(
        select(Address)
        .where(Address.id == address_id)
        .options(
            selectinload(Address.province_region),
            selectinload(Address.city_region),
            selectinload(Address.district_region),
        )
    )
    if address is None:
        raise AppError("ADDRESS_NOT_FOUND", "地址不存在", 404)
    if user.role is Role.CUSTOMER and address.owner_id != user.id:
        raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能访问本人资源", 403)
    return address

async def list_addresses(session: AsyncSession, user: CurrentUser) -> list[Address]:
    """返回正式地址簿条目，过滤掉下单用的一次性临时地址。"""
    result = await session.scalars(
        select(Address)
        .where(Address.owner_id == user.id, Address.ephemeral.is_(False))
        .options(
            selectinload(Address.province_region),
            selectinload(Address.city_region),
            selectinload(Address.district_region),
        )
    )
    return list(result)


async def assign_region_path(
    session: AsyncSession,
    address: Address,
    province_region_id: UUID,
    city_region_id: UUID,
    district_region_id: UUID,
) -> None:
    """以数据库中的区划关系为准写入地址，禁止信任客户端提供的代码。"""
    province, city, district = await resolve_region_path(
        session, province_region_id, city_region_id, district_region_id
    )
    address.province_region_id = province.id
    address.city_region_id = city.id
    address.district_region_id = district.id
    address.district_code = district.code
    address.province_region = province
    address.city_region = city
    address.district_region = district


def address_response(address: Address) -> dict[str, object]:
    """统一生成地址展示字段，避免客户端自行拼接行政区名称。"""
    province = address.province_region
    city = address.city_region
    district = address.district_region
    if province is None or city is None or district is None:
        raise AppError("ADDRESS_REGION_MISSING", "地址缺少有效行政区划", 409)
    names = [province.name]
    if city.name != province.name:
        names.append(city.name)
    names.append(district.name)
    names.append(address.detail)
    return {
        "id": address.id,
        "label": address.label,
        "recipient_name": address.recipient_name,
        "phone": address.phone,
        "province_region_id": province.id,
        "province_name": province.name,
        "city_region_id": city.id,
        "city_name": city.name,
        "district_region_id": district.id,
        "district_name": district.name,
        "district_code": address.district_code,
        "detail": address.detail,
        "full_address": "".join(names),
    }

async def delete_address(session: AsyncSession, address: Address) -> None:
    await session.execute(delete(Address).where(Address.id == address.id))
