from uuid import uuid4

import pytest
from httpx import AsyncClient

from yitu.identity.models import Role, User
from yitu.identity.security import create_access_token, hash_password
from yitu.platform.database import SessionFactory, dispose_database

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> None:
    """每个接口测试前清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()


async def _customer() -> User:
    user = User(
        id=uuid4(),
        login_name=f"customer.{uuid4()}",
        display_name="测试客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    async with SessionFactory() as session, session.begin():
        session.add(user)
    return user


async def test_stations_can_filter_by_service_area(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/stations",
        params={"district_code": "310105", "service_type": "HOME_PICKUP"},
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.json()] == ["SHS-001"]


async def test_customer_address_book_crud(client: AsyncClient) -> None:
    user = await _customer()
    token = create_access_token(user.id, Role.CUSTOMER.value, None)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "label": "家",
        "recipient_name": "张三",
        "phone": "13800000000",
        "district_code": "310105",
        "detail": "虹桥路1号",
    }

    created = await client.post("/api/v1/addresses", json=payload, headers=headers)
    assert created.status_code == 201
    address_id = created.json()["id"]

    listed = await client.get("/api/v1/addresses", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["recipient_name"] == "张三"

    updated = await client.patch(
        f"/api/v1/addresses/{address_id}",
        json={"label": "公司"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "公司"

    deleted = await client.delete(f"/api/v1/addresses/{address_id}", headers=headers)
    assert deleted.status_code == 204


async def test_customer_cannot_access_another_address(client: AsyncClient) -> None:
    owner = await _customer()
    other = await _customer()
    other_token = create_access_token(other.id, Role.CUSTOMER.value, None)
    async with SessionFactory() as session, session.begin():
        from yitu.addresses.models import Address

        address = Address(
            owner_id=owner.id, recipient_name="张三", phone="13800000000",
            district_code="310105", detail="虹桥路1号"
        )
        session.add(address)
    headers = {"Authorization": f"Bearer {other_token}"}
    response = await client.patch(
        f"/api/v1/addresses/{address.id}", json={"label": "盗改"}, headers=headers
    )
    assert response.status_code == 403
