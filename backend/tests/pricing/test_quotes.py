from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from yitu.demo.seed import DEMO_PASSWORD, seed_demo_users
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database
from yitu.pricing.policy import PricingInput, calculate_quote

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    await dispose_database()
    yield
    await dispose_database()


async def test_quote_uses_volume_weight_and_service_fees() -> None:
    result = calculate_quote(
        PricingInput(
            origin_district_code="110101",
            destination_district_code="310105",
            pickup_method="DOOR_PICKUP",
            delivery_method="STATION_PICKUP",
            actual_weight_grams=900,
            length_cm=30,
            width_cm=20,
            height_cm=20,
            declared_value_cents=100_000,
        )
    )

    assert result.rule_version == "pricing-demo-v1"
    assert result.volume_weight_grams == 2_000
    assert result.billable_weight_grams == 2_000
    assert result.total_cents == 3_200
    assert [(item.code, item.amount_cents) for item in result.items] == [
        ("BASE_FEE", 1_500),
        ("ADDITIONAL_WEIGHT", 1_200),
        ("PICKUP_SERVICE", 300),
        ("STATION_PICKUP_DISCOUNT", -100),
        ("INSURANCE", 300),
    ]


async def test_http_quote_snapshot_is_immutable_after_reweigh() -> None:
    from yitu.platform.config import get_settings

    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            login = await client.post("/api/v1/auth/demo-login", json={"login_name": "customer.demo", "password": DEMO_PASSWORD})
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            payload = {"origin_district_code": "110101", "destination_district_code": "310105", "pickup_method": "DOOR_PICKUP", "delivery_method": "HOME_DELIVERY", "actual_weight_grams": 900, "length_cm": 10, "width_cm": 10, "height_cm": 10}
            quote_key = f"quote-{uuid4()}"
            created = await client.post("/api/v1/pricing/quotes", headers={**headers, "Idempotency-Key": quote_key}, json=payload)
            assert created.status_code == 201, created.text
            original = created.json()
            replay = await client.post("/api/v1/pricing/quotes", headers={**headers, "Idempotency-Key": quote_key}, json=payload)
            assert replay.status_code == 201
            assert replay.json()["id"] == original["id"]
            revised = await client.post(f"/api/v1/pricing/quotes/{original['id']}/reweigh", headers=headers, json={"actual_weight_grams": 2500, "length_cm": 10, "width_cm": 10, "height_cm": 10})
            assert revised.status_code == 201, revised.text
            assert revised.json()["id"] != original["id"]
            assert revised.json()["total_cents"] > original["total_cents"]
            fetched = await client.get(f"/api/v1/pricing/quotes/{original['id']}", headers=headers)
            assert fetched.status_code == 200
            assert fetched.json()["total_cents"] == original["total_cents"]
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()
