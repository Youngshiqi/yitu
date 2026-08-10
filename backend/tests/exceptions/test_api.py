from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.exceptions.test_cases import _seed_customer_shipment
from yitu.identity.models import Role
from yitu.identity.security import create_access_token
from yitu.main import create_app
from yitu.platform.database import dispose_database

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


def _headers(user_id: object, role: Role, station_id: object | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user_id, role.value, station_id)}",
    }


async def test_post_exception_requires_idempotency_key() -> None:
    owner, shipment = await _seed_customer_shipment()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/exceptions",
            headers=_headers(owner.id, Role.CUSTOMER),
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "收件地址缺少门牌号",
            },
        )

    assert response.status_code == 422


async def test_customer_can_open_get_and_list_only_own_cases() -> None:
    owner, shipment = await _seed_customer_shipment()
    other_owner, other_shipment = await _seed_customer_shipment()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        opened = await client.post(
            "/api/v1/exceptions",
            headers={**_headers(owner.id, Role.CUSTOMER), "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "收件地址缺少门牌号",
            },
        )
        assert opened.status_code == 201, opened.text
        other = await client.post(
            "/api/v1/exceptions",
            headers={**_headers(other_owner.id, Role.CUSTOMER), "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(other_shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "另一个客户的异常",
            },
        )
        assert other.status_code == 201, other.text

        listed = await client.get(
            "/api/v1/exceptions",
            headers=_headers(owner.id, Role.CUSTOMER),
        )
        detail = await client.get(
            f"/api/v1/exceptions/{opened.json()['id']}",
            headers=_headers(owner.id, Role.CUSTOMER),
        )
        forbidden_detail = await client.get(
            f"/api/v1/exceptions/{other.json()['id']}",
            headers=_headers(owner.id, Role.CUSTOMER),
        )

    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == opened.json()["id"]
    assert detail.status_code == 200
    assert detail.json()["shipment_id"] == str(shipment.id)
    assert forbidden_detail.status_code == 404
