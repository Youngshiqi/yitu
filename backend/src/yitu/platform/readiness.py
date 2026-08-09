import asyncio

from redis.asyncio import Redis
from sqlalchemy import text

from yitu.platform.config import get_settings
from yitu.platform.database import SessionFactory


async def check_readiness() -> None:
    """在限定时间内确认 PostgreSQL 与 Redis 均可用。"""
    async with asyncio.timeout(3):
        await asyncio.gather(_check_postgresql(), _check_redis())


async def _check_postgresql() -> None:
    async with SessionFactory() as session:
        await session.execute(text("SELECT 1"))


async def _check_redis() -> None:
    client = Redis.from_url(get_settings().redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()
