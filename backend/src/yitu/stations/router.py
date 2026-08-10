from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Station
from yitu.platform.database import get_session
from yitu.stations.models import ServiceArea
from yitu.stations.schemas import StationResponse

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])
_session = Depends(get_session)

@router.get("", response_model=list[StationResponse])
async def list_stations(district_code: str | None = Query(default=None), service_type: str | None = Query(default=None), session: AsyncSession = _session) -> list[Station]:
    query = select(Station)
    if service_type is not None:
        query = query.join(ServiceArea, ServiceArea.station_id == Station.id).where(ServiceArea.service_type == service_type)
    if district_code is not None:
        query = query.where(Station.district_code == district_code)
    return list((await session.scalars(query)).all())
