from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Station
from yitu.platform.errors import AppError
from yitu.stations.models import ServiceArea


async def match_station(
    session: AsyncSession, district_code: str, service_type: str
) -> Station:
    """根据区县和服务类型返回确定性网点。"""
    station = (
        await session.execute(
            select(Station)
            .join(ServiceArea, ServiceArea.station_id == Station.id)
            .where(
                ServiceArea.district_code == district_code,
                ServiceArea.service_type == service_type,
            )
        )
    ).scalar_one_or_none()
    if station is None:
        raise AppError(
            code="UNSUPPORTED_SERVICE_AREA",
            message="暂不支持该服务区域",
            status_code=422,
        )
    return station
