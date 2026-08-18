import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "YITU_DATABASE_URL",
    "postgresql+asyncpg://yitu:yitu_local_dev_2026@127.0.0.1:55433/yitu",
)

from yitu.main import create_app
from yitu.platform.config import get_settings
from yitu.platform.database import dispose_database
from yitu.platform.test_cleanup import clean_test_database


@pytest.fixture(scope="session", autouse=True)
async def database_lifecycle() -> AsyncIterator[None]:
    yield
    # 测试结束后清理业务脏数据，避免污染共享开发库（docker db）
    await clean_test_database(get_settings().database_url)
    await dispose_database()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client
