from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from yitu.demo.seed import DEMO_PASSWORD, seed_demo_users
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    await dispose_database()
    yield
    await dispose_database()


async def test_payment_supplement_and_refund_are_idempotent() -> None:
    from yitu.platform.config import get_settings

    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            login = await client.post("/api/v1/auth/demo-login", json={"login_name": "customer.demo", "password": DEMO_PASSWORD})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            address = await client.post("/api/v1/addresses", headers=headers, json={"label": "支付测试", "recipient_name": "张三", "phone": "13800000000", "district_code": "110101", "detail": "演示路1号"})
            address_id = address.json()["id"]
            quote_payload = {"origin_district_code": "110101", "destination_district_code": "310105", "pickup_method": "DOOR_PICKUP", "delivery_method": "HOME_DELIVERY", "actual_weight_grams": 900, "length_cm": 10, "width_cm": 10, "height_cm": 10}
            quote = await client.post("/api/v1/pricing/quotes", headers={**headers, "Idempotency-Key": f"payment-quote-{uuid4()}"}, json=quote_payload)
            assert quote.status_code == 201, quote.text
            quote_data = quote.json()
            shipment = await client.post("/api/v1/shipments", headers={**headers, "Idempotency-Key": f"payment-shipment-{uuid4()}"}, json={"draft": {"sender_address_id": address_id, "receiver_address_id": address_id, "pickup_method": "DOOR_PICKUP", "delivery_method": "HOME_DELIVERY"}})
            assert shipment.status_code == 201, shipment.text
            shipment_data = shipment.json()
            shipment_id = shipment_data["id"]
            payment_key = f"payment-{uuid4()}"
            paid = await client.post(f"/api/v1/payments/quotes/{quote_data['id']}/pay", headers={**headers, "Idempotency-Key": payment_key}, json={"shipment_id": shipment_id, "amount_cents": quote_data["total_cents"]})
            assert paid.status_code == 201, paid.text
            replay = await client.post(f"/api/v1/payments/quotes/{quote_data['id']}/pay", headers={**headers, "Idempotency-Key": payment_key}, json={"shipment_id": shipment_id, "amount_cents": quote_data["total_cents"]})
            assert replay.status_code == 201
            assert replay.json()["id"] == paid.json()["id"]
            wrong_amount = await client.post(f"/api/v1/payments/quotes/{quote_data['id']}/pay", headers={**headers, "Idempotency-Key": f"wrong-{uuid4()}"}, json={"shipment_id": shipment_id, "amount_cents": quote_data["total_cents"] - 1})
            assert wrong_amount.status_code == 409
            revised = await client.post(f"/api/v1/pricing/quotes/{quote_data['id']}/reweigh", headers=headers, json={"actual_weight_grams": 2500, "length_cm": 10, "width_cm": 10, "height_cm": 10})
            assert revised.status_code == 201, revised.text
            supplement = await client.post(f"/api/v1/payments/quotes/{revised.json()['id']}/supplement", headers={**headers, "Idempotency-Key": f"supplement-{uuid4()}"}, json={"shipment_id": shipment_id, "amount_cents": revised.json()["total_cents"] - quote_data["total_cents"]})
            assert supplement.status_code == 201, supplement.text
            refund = await client.post(f"/api/v1/payments/transactions/{paid.json()['id']}/refund", headers={**headers, "Idempotency-Key": f"refund-{uuid4()}"})
            assert refund.status_code == 201, refund.text
            shipment_state = await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)
            assert shipment_state.json()["status"] == "CANCELLED"
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()

    async with SessionFactory() as session:
        notification_payload = (
            await session.execute(
                text(
                    "SELECT payload FROM outbox_events "
                    "WHERE event_type = 'notification.requested' "
                    "AND business_id = :business_id"
                ),
                {"business_id": f"shipment:{shipment_id}"},
            )
        ).scalar_one()
    assert notification_payload == {
        "recipient_id": "30000000-0000-4000-8000-000000000001",
        "template_code": "PAYMENT_SUCCESS",
        "template_data": {"shipment_no": shipment_data["shipment_no"]},
    }
