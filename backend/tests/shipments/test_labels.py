from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.exceptions.test_api import _headers
from yitu.addresses.models import Address
from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.labels.service import LabelService
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def test_label_projection_excludes_personal_sensitive_information() -> None:
    customer = User(
        id=uuid4(),
        login_name=f"label.customer.{uuid4()}",
        display_name="面单客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    sender = Address(
        owner_id=customer.id,
        recipient_name="张三",
        phone="13800000000",
        district_code="310105",
        detail="长宁路 100 号 201 室",
    )
    receiver = Address(
        owner_id=customer.id,
        recipient_name="李四",
        phone="13900000000",
        district_code="110101",
        detail="东长安街 1 号",
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        sender_address_id=sender.id,
        receiver_address_id=receiver.id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        session.add(customer)
        await session.flush()
        session.add_all([sender, receiver])
        await session.flush()
        session.add(shipment)

    async with SessionFactory() as session:
        projection = await LabelService(session).project(shipment.id)

    serialized = projection.model_dump_json()
    assert projection.code128_value == shipment.shipment_no
    assert shipment.shipment_no in projection.qr_payload
    assert len(projection.qr_token) == 32
    for sensitive in ["张三", "李四", "13800000000", "13900000000", "长宁路", "东长安街"]:
        assert sensitive not in serialized


async def test_customer_can_fetch_safe_label_projection_via_api() -> None:
    customer = User(
        id=uuid4(),
        login_name=f"label.api.customer.{uuid4()}",
        display_name="面单 API 客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        session.add(customer)
        await session.flush()
        session.add(shipment)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/api/v1/shipments/{shipment.id}/label",
            headers=_headers(customer.id, Role.CUSTOMER),
        )

    assert response.status_code == 200, response.text
    assert response.json()["code128_value"] == shipment.shipment_no
    assert "qr_token" in response.json()
