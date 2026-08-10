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


class JourneyClient:
    """仅通过 HTTP 调用模拟客户、快递员和网点员的物流旅程。"""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self._tokens: dict[str, str] = {}

    async def login(self, login_name: str) -> None:
        response = await self._client.post(
            "/api/v1/auth/demo-login",
            json={"login_name": login_name, "password": DEMO_PASSWORD},
        )
        assert response.status_code == 200, response.text
        self._tokens[login_name] = response.json()["access_token"]

    def headers(self, login_name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tokens[login_name]}"}

    async def request(self, method: str, path: str, login_name: str, **kwargs):
        headers = {**self.headers(login_name), **kwargs.pop("headers", {})}
        response = await self._client.request(method, path, headers=headers, **kwargs)
        assert response.status_code < 400, response.text
        return response

    async def station_id(self, district_code: str) -> str:
        response = await self._client.get("/api/v1/stations", params={"district_code": district_code})
        assert response.status_code == 200, response.text
        return response.json()[0]["id"]

    async def address(self, district_code: str) -> str:
        response = await self.request(
            "POST", "/api/v1/addresses", "customer.demo",
            json={"label": "演示地址", "recipient_name": "张三", "phone": "13800000000", "district_code": district_code, "detail": "演示路 1 号"},
        )
        return response.json()["id"]

    async def task_id(self, shipment_id: str, task_type: str, login_name: str) -> str:
        response = await self.request("GET", "/api/v1/dispatch/tasks", login_name, params={"shipment_id": shipment_id})
        return next(item["id"] for item in response.json() if item["task_type"] == task_type)


@pytest.mark.parametrize(
    ("pickup_method", "delivery_method"),
    [
        ("DOOR_PICKUP", "HOME_DELIVERY"),
        ("DOOR_PICKUP", "STATION_PICKUP"),
        ("STATION_DROPOFF", "HOME_DELIVERY"),
        ("STATION_DROPOFF", "STATION_PICKUP"),
    ],
)
async def test_four_service_combinations_reach_terminal_state(pickup_method: str, delivery_method: str) -> None:
    from yitu.platform.config import get_settings

    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as http:
            journey = JourneyClient(http)
            for login_name in ("customer.demo", "courier.bijing.demo", "courier.shanghai.demo", "operator.beijing.demo", "operator.shanghai.demo", "operations.demo"):
                await journey.login(login_name)
            origin_station_id = await journey.station_id("110101")
            destination_station_id = await journey.station_id("310105")
            draft = {"pickup_method": pickup_method, "delivery_method": delivery_method}
            if pickup_method == "DOOR_PICKUP":
                draft["sender_address_id"] = await journey.address("110101")
            else:
                draft["origin_station_id"] = origin_station_id
            if delivery_method == "HOME_DELIVERY":
                draft["receiver_address_id"] = await journey.address("310105")
            else:
                draft["destination_station_id"] = destination_station_id
            shipment = await journey.request("POST", "/api/v1/shipments", "customer.demo", headers={"Idempotency-Key": f"journey-http-{uuid4()}"}, json={"draft": draft})
            shipment_id = shipment.json()["id"]
            await journey.request("POST", f"/api/v1/shipments/{shipment_id}/confirm-payment", "customer.demo")
            if pickup_method == "DOOR_PICKUP":
                task_id = await journey.task_id(shipment_id, "PICKUP", "courier.bijing.demo")
                await journey.request("POST", f"/api/v1/dispatch/tasks/{task_id}/accept", "courier.bijing.demo")
                await journey.request("POST", f"/api/v1/dispatch/tasks/{task_id}/confirm-pickup", "courier.bijing.demo")
                await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/confirm-origin-arrival", "operator.beijing.demo")
            else:
                await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/accept-dropoff", "operator.beijing.demo")
            await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/dispatch-linehaul", "operator.beijing.demo")
            await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/arrive-destination", "operations.demo")
            if delivery_method == "HOME_DELIVERY":
                task_id = await journey.task_id(shipment_id, "DELIVERY", "courier.shanghai.demo")
                await journey.request("POST", f"/api/v1/dispatch/tasks/{task_id}/accept", "courier.shanghai.demo")
                await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/start-delivery", "courier.shanghai.demo")
                await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/confirm-delivery", "courier.shanghai.demo", json={"signer_name": "张三"})
            else:
                issued = await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/issue-pickup-credential", "operator.shanghai.demo")
                assert "123456" not in issued.text
                await journey.request("POST", f"/api/v1/dispatch/shipments/{shipment_id}/verify-station-pickup", "operator.shanghai.demo", json={"code": "123456"})
            result = await journey.request("GET", f"/api/v1/shipments/{shipment_id}", "customer.demo")
            assert result.json()["status"] == "DELIVERED"
            tracking = await journey.request("GET", f"/api/v1/shipments/{shipment_id}/tracking", "customer.demo")
            sequence_numbers = [event["sequence_no"] for event in tracking.json()]
            assert sequence_numbers == sorted(sequence_numbers)
            assert "123456" not in tracking.text
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()


async def test_http_authorization_rejects_non_owner_and_cross_station_courier() -> None:
    """确认支付和揽收接单分别受所有权、网点范围约束。"""
    from yitu.platform.config import get_settings

    async with SessionFactory() as session, session.begin():
        await seed_demo_users(session)
    settings = get_settings()
    original_profile = settings.app_profile
    settings.app_profile = "demo"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as http:
            journey = JourneyClient(http)
            for login_name in ("customer.demo", "courier.bijing.demo", "courier.shanghai.demo", "operator.beijing.demo"):
                await journey.login(login_name)
            sender_id = await journey.address("110101")
            receiver_id = await journey.address("310105")
            shipment = await journey.request("POST", "/api/v1/shipments", "customer.demo", headers={"Idempotency-Key": f"authorization-{uuid4()}"}, json={"draft": {"sender_address_id": sender_id, "receiver_address_id": receiver_id, "pickup_method": "DOOR_PICKUP", "delivery_method": "HOME_DELIVERY"}})
            shipment_id = shipment.json()["id"]
            forbidden_payment = await http.post(f"/api/v1/shipments/{shipment_id}/confirm-payment", headers=journey.headers("operator.beijing.demo"))
            assert forbidden_payment.status_code == 403
            await journey.request("POST", f"/api/v1/shipments/{shipment_id}/confirm-payment", "customer.demo")
            task_id = await journey.task_id(shipment_id, "PICKUP", "courier.bijing.demo")
            cross_station_accept = await http.post(f"/api/v1/dispatch/tasks/{task_id}/accept", headers=journey.headers("courier.shanghai.demo"))
            assert cross_station_accept.status_code == 403
    finally:
        settings.app_profile = original_profile
        get_settings.cache_clear()
