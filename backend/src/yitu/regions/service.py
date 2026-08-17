from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.errors import AppError
from yitu.regions.models import AdministrativeRegion, RegionLevel


async def list_regions(
    session: AsyncSession,
    *,
    level: RegionLevel | None,
    parent_id: UUID | None,
) -> list[AdministrativeRegion]:
    """按层级或父节点返回启用区域，避免一次向客户端发送全国数据。"""
    statement = select(AdministrativeRegion).where(AdministrativeRegion.enabled.is_(True))
    if parent_id is not None:
        statement = statement.where(AdministrativeRegion.parent_id == parent_id)
    elif level is RegionLevel.PROVINCE:
        statement = statement.where(
            AdministrativeRegion.level == RegionLevel.PROVINCE,
            AdministrativeRegion.parent_id.is_(None),
        )
    else:
        raise AppError("REGION_QUERY_INVALID", "必须指定省级层级或上级区域", 422)
    result = await session.scalars(statement.order_by(AdministrativeRegion.code))
    return list(result)


# 常见行政后缀按「长后缀优先」排序，规范化时只去掉一个，避免「自治区」误伤「区」。
_REGION_SUFFIXES = (
    "特别行政区",
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "自治区",
    "自治州",
    "自治县",
    "自治旗",
    "地区",
    "省",
    "市",
    "区",
    "县",
    "旗",
    "盟",
)


def _normalize_region_name(name: str) -> str:
    """去除行政区划名称的常见后缀，供口语地址（如「北京」「朝阳」）模糊匹配。"""
    normalized = name.strip()
    for suffix in _REGION_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


async def _find_region_by_name(
    session: AsyncSession,
    level: RegionLevel,
    name: str,
    parent_id: UUID | None,
) -> AdministrativeRegion | None:
    """在指定层级（可选限定父节点）内按规范化名称唯一匹配区域。"""
    target = _normalize_region_name(name)
    statement = select(AdministrativeRegion).where(
        AdministrativeRegion.level == level,
        AdministrativeRegion.enabled.is_(True),
    )
    if parent_id is not None:
        statement = statement.where(AdministrativeRegion.parent_id == parent_id)
    regions = list((await session.scalars(statement)).all())
    matches = [
        region for region in regions if _normalize_region_name(region.name) == target
    ]
    return matches[0] if len(matches) == 1 else None


async def resolve_region_by_names(
    session: AsyncSession,
    province_name: str,
    city_name: str,
    district_name: str,
) -> tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion]:
    """按省/市/区县名称逐层解析并校验父子关系，供对话口述地址落库。"""
    province = await _find_region_by_name(
        session, RegionLevel.PROVINCE, province_name, None
    )
    if province is None:
        raise AppError("REGION_NOT_FOUND", f"未找到省份「{province_name}」", 422)
    city = await _find_region_by_name(
        session, RegionLevel.CITY, city_name, province.id
    )
    if city is None:
        raise AppError("REGION_NOT_FOUND", f"未找到城市「{city_name}」", 422)
    district = await _find_region_by_name(
        session, RegionLevel.DISTRICT, district_name, city.id
    )
    if district is None:
        raise AppError("REGION_NOT_FOUND", f"未找到区县「{district_name}」", 422)
    return province, city, district


async def resolve_region_path(
    session: AsyncSession,
    province_id: UUID,
    city_id: UUID,
    district_id: UUID,
) -> tuple[AdministrativeRegion, AdministrativeRegion, AdministrativeRegion]:
    """校验省、市、区县均启用且具有严格的父子关系。"""
    regions = {
        region.id: region
        for region in (
            await session.scalars(
                select(AdministrativeRegion).where(
                    AdministrativeRegion.id.in_([province_id, city_id, district_id])
                )
            )
        ).all()
    }
    province = regions.get(province_id)
    city = regions.get(city_id)
    district = regions.get(district_id)
    if province is None or city is None or district is None:
        raise AppError("REGION_NOT_FOUND", "所选行政区域不存在", 422)
    if not province.enabled or not city.enabled or not district.enabled:
        raise AppError("REGION_DISABLED", "所选行政区域已停用", 422)
    if (
        province.level != RegionLevel.PROVINCE
        or city.level != RegionLevel.CITY
        or district.level != RegionLevel.DISTRICT
        or city.parent_id != province.id
        or district.parent_id != city.id
    ):
        raise AppError("INVALID_REGION_HIERARCHY", "省、市、区县不属于同一行政区划链", 422)
    return province, city, district
