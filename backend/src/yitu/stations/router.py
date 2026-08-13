from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role, Station
from yitu.identity.service import CurrentUser, get_current_user, require_roles
from yitu.platform.database import get_session
from yitu.stations.admin_service import (
    create_station,
    delete_station,
    get_admin_station,
    list_admin_stations,
    set_station_enabled,
    update_station,
)
from yitu.stations.models import ServiceArea
from yitu.stations.schemas import (
    StationAdminList,
    StationAdminView,
    StationCreate,
    StationResponse,
    StationUpdate,
)

router = APIRouter(tags=["stations"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


def operations_user(current_user: CurrentUser = _current_user) -> CurrentUser:
    return require_roles(Role.OPERATIONS_ADMIN)(current_user)


_operations = Depends(operations_user)


@router.get("/api/v1/stations", response_model=list[StationResponse])
async def list_stations(
    district_code: str | None = Query(default=None),
    service_type: str | None = Query(default=None),
    session: AsyncSession = _session,
) -> list[Station]:
    """返回参与新业务的启用网点。"""
    query = select(Station).where(Station.enabled.is_(True))
    if service_type is not None or district_code is not None:
        query = query.join(ServiceArea, ServiceArea.station_id == Station.id)
    if service_type is not None:
        query = query.where(ServiceArea.service_type == service_type)
    if district_code is not None:
        query = query.where(ServiceArea.district_code == district_code)
    return list((await session.scalars(query.distinct().order_by(Station.code))).all())


@router.get("/api/v1/admin/stations", response_model=StationAdminList)
async def admin_list_stations(
    query: Annotated[str | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminList:
    items, total = await list_admin_stations(
        session, query=query, enabled=enabled, limit=limit, offset=offset
    )
    return StationAdminList(items=items, total=total)


@router.post(
    "/api/v1/admin/stations",
    response_model=StationAdminView,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_station(
    payload: StationCreate,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminView:
    result = await create_station(session, payload)
    await session.commit()
    return result


@router.get("/api/v1/admin/stations/{station_id}", response_model=StationAdminView)
async def admin_get_station(
    station_id: UUID,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminView:
    return await get_admin_station(session, station_id)


@router.patch("/api/v1/admin/stations/{station_id}", response_model=StationAdminView)
async def admin_update_station(
    station_id: UUID,
    payload: StationUpdate,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminView:
    result = await update_station(session, station_id, payload)
    await session.commit()
    return result


@router.post(
    "/api/v1/admin/stations/{station_id}/enable", response_model=StationAdminView
)
async def admin_enable_station(
    station_id: UUID,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminView:
    result = await set_station_enabled(session, station_id, True)
    await session.commit()
    return result


@router.post(
    "/api/v1/admin/stations/{station_id}/disable", response_model=StationAdminView
)
async def admin_disable_station(
    station_id: UUID,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> StationAdminView:
    result = await set_station_enabled(session, station_id, False)
    await session.commit()
    return result


@router.delete(
    "/api/v1/admin/stations/{station_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def admin_delete_station(
    station_id: UUID,
    _user: CurrentUser = _operations,
    session: AsyncSession = _session,
) -> Response:
    await delete_station(session, station_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
