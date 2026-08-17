import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from yitu.addresses.models import Address
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.regions.service import resolve_region_path

_PHONE_NON_DIGIT = re.compile(r"\D+")
_WHITESPACE = re.compile(r"\s+")


def normalize_phone(value: str) -> str:
    """手机号归一化为可比较的纯数字串，消除空格、连字符、国家码等格式差异。"""
    digits = _PHONE_NON_DIGIT.sub("", value or "")
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    elif digits.startswith("0086"):
        digits = digits[4:]
    return digits


def normalize_address_text(value: str) -> str:
    """地址文本归一化：NFKC 全半角统一 + 去全部空白，忽略空格排版差异。"""
    normalized = unicodedata.normalize("NFKC", value or "")
    return _WHITESPACE.sub("", normalized)


async def find_matching_address(
    session: AsyncSession,
    owner_id: UUID,
    recipient_name: str,
    phone: str,
    district_region_id: UUID,
    detail: str,
) -> Address | None:
    """按归一化五元组查找既有地址，优先返回正式条目和更早创建的记录。

    姓名、手机号、门牌做归一化后精确比较（手机号去格式与国家码、文本去空白与全半角差异）；
    命中即视为同一地址，调用方应复用而非新建。
    """
    want_name = normalize_address_text(recipient_name)
    want_phone = normalize_phone(phone)
    want_detail = normalize_address_text(detail)
    candidates = await session.scalars(
        select(Address)
        .where(
            Address.owner_id == owner_id,
            Address.district_region_id == district_region_id,
            Address.deleted_at.is_(None),
        )
        .order_by(Address.ephemeral.asc(), Address.id.asc())
    )
    for address in candidates:
        if normalize_address_text(address.recipient_name) != want_name:
            continue
        if normalize_phone(address.phone) != want_phone:
            continue
        if normalize_address_text(address.detail) != want_detail:
            continue
        return address
    return None


async def get_owned_address(session: AsyncSession, address_id: UUID, user: CurrentUser) -> Address:
    address = await session.scalar(
        select(Address)
        .where(Address.id == address_id, Address.deleted_at.is_(None))
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
    """返回正式地址簿条目，过滤掉下单用的一次性临时地址与已软删除条目。"""
    result = await session.scalars(
        select(Address)
        .where(
            Address.owner_id == user.id,
            Address.ephemeral.is_(False),
            Address.deleted_at.is_(None),
        )
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
    """软删除地址：仅打 deleted_at 标记，保留物理行供历史运单外键引用。"""
    address.deleted_at = Clock.now()
