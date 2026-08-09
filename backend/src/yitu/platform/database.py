from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from yitu.platform.config import get_settings
from yitu.platform.models import Base

__all__ = [
    "Base",
    "SessionFactory",
    "dispose_database",
    "get_session",
    "transactional_session",
]

_settings = get_settings()
_engine = create_async_engine(
    _settings.database_url,
    connect_args={"server_settings": {"timezone": _settings.business_timezone}},
)

SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_database() -> None:
    """关闭连接池中的数据库连接，供应用或测试生命周期结束时调用。"""
    await _engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """为 FastAPI 依赖提供一次请求范围内的数据库会话。"""
    async with SessionFactory() as session:
        yield session


@asynccontextmanager
async def transactional_session() -> AsyncIterator[AsyncSession]:
    """提供成功时提交、发生异常时回滚的事务会话。"""
    async with SessionFactory() as session, session.begin():
        yield session
