from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.main import create_app
from yitu.platform.config import get_settings
from yitu.platform.database import SessionFactory


@pytest.fixture
async def demo_user() -> User:
    user = User(
        id=uuid4(),
        login_name="customer.auth.test",
        display_name="认证测试客户",
        password_hash=hash_password("正确密码"),
        role=Role.CUSTOMER,
        demo_key="customer-auth-test",
    )
    async with SessionFactory() as session, session.begin():
        session.add(user)
    yield user
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(User).where(User.id == user.id))


async def test_demo_login_and_me_return_current_identity(
    demo_user: User,
) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            login = await client.post(
                "/api/v1/auth/demo-login",
                json={"login_name": demo_user.login_name, "password": "正确密码"},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]

            me = await client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert me.status_code == 200
            assert me.json() == {
                "id": str(demo_user.id),
                "display_name": "认证测试客户",
                "role": "CUSTOMER",
                "station_id": None,
            }
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()


async def test_demo_login_is_hidden_outside_demo_profile() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.app_profile = "development"
    try:
        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/auth/demo-login",
                json={"login_name": "anything", "password": "anything"},
            )
        assert response.status_code == 404
    finally:
        get_settings.cache_clear()
