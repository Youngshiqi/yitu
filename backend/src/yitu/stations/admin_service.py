from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Station
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.regions.models import AdministrativeRegion, RegionLevel
from yitu.stations.models import ServiceArea
from yitu.stations.schemas import (
    ServiceAreaInput,
    ServiceAreaView,
    ServiceType,
    StationAdminView,
    StationCreate,
    StationUpdate,
)


async def _district(session: AsyncSession, region_id: UUID) -> AdministrativeRegion:
    region = await session.get(AdministrativeRegion, region_id)
    if region is None or region.level != RegionLevel.DISTRICT:
        raise AppError("REGION_NOT_FOUND", "所选区县不存在", 422)
    if not region.enabled:
        raise AppError("REGION_DISABLED", "所选区县已停用", 422)
    return region


async def _region_names(
    session: AsyncSession, districts: list[AdministrativeRegion]
) -> dict[UUID, tuple[UUID, UUID, str, str, str]]:
    city_ids = {item.parent_id for item in districts if item.parent_id is not None}
    cities = {
        item.id: item
        for item in (
            await session.scalars(
                select(AdministrativeRegion).where(AdministrativeRegion.id.in_(city_ids))
            )
        ).all()
    }
    province_ids = {item.parent_id for item in cities.values() if item.parent_id is not None}
    provinces = {
        item.id: item
        for item in (
            await session.scalars(
                select(AdministrativeRegion).where(
                    AdministrativeRegion.id.in_(province_ids)
                )
            )
        ).all()
    }
    result: dict[UUID, tuple[UUID, UUID, str, str, str]] = {}
    for district in districts:
        if district.parent_id is None:
            continue
        city = cities.get(district.parent_id)
        if city is None or city.parent_id is None:
            continue
        province = provinces.get(city.parent_id)
        if province is None:
            continue
        result[district.id] = (
            province.id,
            city.id,
            province.name,
            city.name,
            district.name,
        )
    return result


async def _views(
    session: AsyncSession, stations: list[Station]
) -> list[StationAdminView]:
    if not stations:
        return []
    station_ids = [item.id for item in stations]
    areas = list(
        (
            await session.scalars(
                select(ServiceArea).where(ServiceArea.station_id.in_(station_ids))
            )
        ).all()
    )
    district_codes = {item.district_code for item in stations} | {
        item.district_code for item in areas
    }
    districts = list(
        (
            await session.scalars(
                select(AdministrativeRegion).where(
                    AdministrativeRegion.level == RegionLevel.DISTRICT,
                    AdministrativeRegion.code.in_(district_codes),
                )
            )
        ).all()
    )
    district_by_code = {item.code: item for item in districts}
    names = await _region_names(session, districts)
    grouped: dict[UUID, dict[str, list[ServiceType]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for area in areas:
        grouped[area.station_id][area.district_code].append(ServiceType(area.service_type))
    result: list[StationAdminView] = []
    for station in stations:
        location = district_by_code[station.district_code]
        province_id, city_id, province_name, city_name, district_name = names[location.id]
        service_views = []
        for code, types in grouped[station.id].items():
            district = district_by_code[code]
            area_province_id, area_city_id, province, city, name = names[district.id]
            service_views.append(
                ServiceAreaView(
                    province_region_id=area_province_id,
                    city_region_id=area_city_id,
                    district_region_id=district.id,
                    district_code=code,
                    district_name=name,
                    province_name=province,
                    city_name=city,
                    service_types=sorted(types, key=str),
                )
            )
        result.append(
            StationAdminView(
                id=station.id,
                code=station.code,
                name=station.name,
                district_code=station.district_code,
                province_region_id=province_id,
                city_region_id=city_id,
                district_region_id=location.id,
                district_name=district_name,
                province_name=province_name,
                city_name=city_name,
                enabled=station.enabled,
                created_at=station.created_at,
                updated_at=station.updated_at,
                service_areas=service_views,
            )
        )
    return result


async def list_admin_stations(
    session: AsyncSession,
    *,
    query: str | None,
    enabled: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[StationAdminView], int]:
    filters = []
    if query:
        filters.append(or_(Station.code.ilike(f"%{query}%"), Station.name.ilike(f"%{query}%")))
    if enabled is not None:
        filters.append(Station.enabled.is_(enabled))
    total = await session.scalar(select(func.count()).select_from(Station).where(*filters))
    stations = list(
        (
            await session.scalars(
                select(Station)
                .where(*filters)
                .order_by(Station.code)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return await _views(session, stations), int(total or 0)


async def get_admin_station(session: AsyncSession, station_id: UUID) -> StationAdminView:
    station = await session.get(Station, station_id)
    if station is None:
        raise AppError("STATION_NOT_FOUND", "网点不存在", 404)
    return (await _views(session, [station]))[0]


async def _replace_service_areas(
    session: AsyncSession,
    station: Station,
    inputs: list[ServiceAreaInput],
) -> None:
    desired: dict[tuple[str, ServiceType], AdministrativeRegion] = {}
    for item in inputs:
        district = await _district(session, item.district_region_id)
        # 服务区默认提供门到门服务，不再由运营员逐项选择服务类型。
        for service_type in (ServiceType.HOME_PICKUP, ServiceType.HOME_DELIVERY):
            desired[(district.code, service_type)] = district
    if desired:
        conflicts = list(
            (
                await session.scalars(
                    select(ServiceArea).where(
                        ServiceArea.station_id != station.id,
                        or_(
                            *[
                                (ServiceArea.district_code == code)
                                & (ServiceArea.service_type == service_type)
                                for code, service_type in desired
                            ]
                        ),
                    )
                )
            ).all()
        )
        if conflicts:
            conflict = conflicts[0]
            owner = await session.get(Station, conflict.station_id)
            district = desired[(conflict.district_code, ServiceType(conflict.service_type))]
            raise AppError(
                "SERVICE_AREA_CONFLICT",
                f"{district.name}的{ServiceType(conflict.service_type).value}已属于网点{owner.name if owner else conflict.station_id}",
                409,
            )
    await session.execute(delete(ServiceArea).where(ServiceArea.station_id == station.id))
    session.add_all(
        ServiceArea(
            district_code=code,
            service_type=service_type.value,
            station_id=station.id,
            version=1,
        )
        for code, service_type in desired
    )


async def create_station(session: AsyncSession, payload: StationCreate) -> StationAdminView:
    if await session.scalar(select(Station.id).where(Station.code == payload.code)):
        raise AppError("STATION_CODE_CONFLICT", "网点编码已存在", 409)
    district = await _district(session, payload.district_region_id)
    station = Station(code=payload.code, name=payload.name, district_code=district.code)
    session.add(station)
    await session.flush()
    service_areas = payload.service_areas or [
        ServiceAreaInput(
            district_region_id=payload.district_region_id,
            service_types=[ServiceType.HOME_PICKUP, ServiceType.HOME_DELIVERY],
        )
    ]
    await _replace_service_areas(session, station, service_areas)
    await session.flush()
    return await get_admin_station(session, station.id)


async def update_station(
    session: AsyncSession, station_id: UUID, payload: StationUpdate
) -> StationAdminView:
    station = await session.get(Station, station_id)
    if station is None:
        raise AppError("STATION_NOT_FOUND", "网点不存在", 404)
    if payload.code is not None and payload.code != station.code:
        if await session.scalar(select(Station.id).where(Station.code == payload.code)):
            raise AppError("STATION_CODE_CONFLICT", "网点编码已存在", 409)
        station.code = payload.code
    if payload.name is not None:
        station.name = payload.name
    if payload.district_region_id is not None:
        station.district_code = (await _district(session, payload.district_region_id)).code
        if payload.service_areas is None:
            await _replace_service_areas(
                session,
                station,
                [
                    ServiceAreaInput(
                        district_region_id=payload.district_region_id,
                        service_types=[
                            ServiceType.HOME_PICKUP,
                            ServiceType.HOME_DELIVERY,
                        ],
                    )
                ],
            )
    if payload.service_areas is not None:
        await _replace_service_areas(session, station, payload.service_areas)
    station.updated_at = Clock.now()
    await session.flush()
    return await get_admin_station(session, station.id)


async def set_station_enabled(
    session: AsyncSession, station_id: UUID, enabled: bool
) -> StationAdminView:
    station = await session.get(Station, station_id)
    if station is None:
        raise AppError("STATION_NOT_FOUND", "网点不存在", 404)
    station.enabled = enabled
    station.updated_at = Clock.now()
    await session.flush()
    return await get_admin_station(session, station.id)


async def delete_station(session: AsyncSession, station_id: UUID) -> None:
    station = await session.get(Station, station_id)
    if station is None:
        raise AppError("STATION_NOT_FOUND", "网点不存在", 404)
    await session.execute(delete(ServiceArea).where(ServiceArea.station_id == station.id))
    await session.delete(station)
    try:
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        raise AppError("STATION_IN_USE", "网点已被业务数据引用，请改为停用", 409) from error
