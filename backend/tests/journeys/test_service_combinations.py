from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from yitu.demo.seed import DEMO_PASSWORD, seed_demo_users
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    await dispose_database()
    yield
    await dispose_database()


async def _login(client: AsyncClient, login_name: str) -> str:
    response = await client.post("/api/v1/auth/demo-login", json={"login_name": login_name, "password": DEMO_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_demo_seed_and_http_shipment_entrypoints(client) -> None:
    from yitu.platform.config import get_settings

    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as http:
            token = await _login(http, "customer.demo")
            headers = {"Authorization": f"Bearer {token}"}
            address = await http.post("/api/v1/addresses", headers=headers, json={"label": "家", "recipient_name": "张三", "phone": "13800000000", "district_code": "110101", "detail": "朝阳路1号"})
            assert address.status_code == 201
            shipment = await http.post("/api/v1/shipments", headers={**headers, "Idempotency-Key": f"journey-http-{uuid4()}"}, json={"draft": {"sender_address_id": address.json()["id"], "receiver_address_id": address.json()["id"], "pickup_method": "DOOR_PICKUP", "delivery_method": "HOME_DELIVERY"}})
            assert shipment.status_code == 201
            paid = await http.post(f"/api/v1/shipments/{shipment.json()['id']}/confirm-payment", headers=headers)
            assert paid.status_code == 204
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()
