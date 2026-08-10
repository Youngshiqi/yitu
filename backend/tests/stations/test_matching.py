import pytest

from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.stations.service import match_station

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> None:
    """每个测试前清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()


@pytest.mark.parametrize(
    ("district_code", "service_type", "station_code"),
    [
        ("110101", "HOME_PICKUP", "BJS-001"),
        ("310105", "HOME_PICKUP", "SHS-001"),
        ("440106", "HOME_PICKUP", "GZS-001"),
        ("440305", "HOME_PICKUP", "SZS-001"),
        ("310105", "STATION_DROP_OFF", "SHS-001"),
    ],
)
async def test_match_station_is_deterministic(
    district_code: str, service_type: str, station_code: str
) -> None:
    async with SessionFactory() as session:
        station = await match_station(session, district_code, service_type)

    assert station.code == station_code


async def test_match_station_rejects_unsupported_district() -> None:
    async with SessionFactory() as session:
        with pytest.raises(AppError, match="暂不支持该服务区域"):
            await match_station(session, "999999", "HOME_PICKUP")
