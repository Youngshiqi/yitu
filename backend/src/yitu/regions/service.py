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
