from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role, Station, User
from yitu.identity.security import create_access_token, hash_password
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


def _headers(user_id: object, role: Role, station_id: object | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user_id, role.value, station_id)}",
    }


async def _seed_shipments() -> tuple[User, User, User, list[str]]:
    first_owner = User(
        id=uuid4(),
        login_name=f"shipments.first.{uuid4()}",
        display_name="运单列表客户 A",
        password_hash=hash_password("password"),
        role=Role.CUSTOMER,
    )
    second_owner = User(
        id=uuid4(),
        login_name=f"shipments.second.{uuid4()}",
        display_name="运单列表客户 B",
        password_hash=hash_password("password"),
        role=Role.CUSTOMER,
    )
    admin = User(
        id=uuid4(),
        login_name=f"shipments.admin.{uuid4()}",
        display_name="运单列表运营",
        password_hash=hash_password("password"),
        role=Role.OPERATIONS_ADMIN,
    )
    marker = uuid4().hex[:8].upper()
    shipment_nos = [
        f"YT-LIST-{marker}-003",
        f"YT-LIST-{marker}-002",
        f"YT-LIST-{marker}-001",
    ]
    async with SessionFactory() as session, session.begin():
        session.add_all([first_owner, second_owner, admin])
        await session.flush()
        session.add_all(
            [
                _shipment(first_owner.id, shipment_nos[0], ShipmentStatus.DELIVERED),
                _shipment(
                    first_owner.id,
                    shipment_nos[1],
                    ShipmentStatus.PENDING_PAYMENT,
                ),
                _shipment(
                    second_owner.id,
                    shipment_nos[2],
                    ShipmentStatus.PENDING_PAYMENT,
                ),
            ]
        )
    return first_owner, second_owner, admin, shipment_nos


def _shipment(owner_id: UUID, shipment_no: str, status: ShipmentStatus) -> Shipment:
    return Shipment(
        shipment_no=shipment_no,
        owner_id=owner_id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=status,
    )


async def test_customer_lists_only_owned_shipments_with_status_filter() -> None:
    owner, _other_owner, _admin, shipment_nos = await _seed_shipments()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/shipments?status=PENDING_PAYMENT",
            headers=_headers(owner.id, Role.CUSTOMER),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [item["shipment_no"] for item in body["items"]] == [shipment_nos[1]]


async def test_operations_admin_can_page_all_shipments() -> None:
    _owner, _other_owner, admin, shipment_nos = await _seed_shipments()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/shipments?status=PENDING_PAYMENT&limit=100",
            headers=_headers(admin.id, Role.OPERATIONS_ADMIN),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    returned_nos = {item["shipment_no"] for item in body["items"]}
    assert body["total"] >= 2
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert {shipment_nos[1], shipment_nos[2]}.issubset(returned_nos)


async def test_courier_cannot_list_shipments() -> None:
    owner, _other_owner, _admin, _shipment_nos = await _seed_shipments()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/shipments",
            headers=_headers(owner.id, Role.COURIER),
        )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN_ROLE"


async def test_shipment_detail_is_visible_to_all_in_scope_roles() -> None:
    station = Station(code=f"DETAIL-{uuid4().hex[:8]}", name="详情网点", district_code="310105")
    destination_station = Station(code=f"DETAIL-DST-{uuid4().hex[:8]}", name="目的网点", district_code="310106")
    owner = User(
        login_name=f"shipments.owner.{uuid4()}",
        display_name="运单客户",
        password_hash=hash_password("password"),
        role=Role.CUSTOMER,
    )
    operator = User(
        login_name=f"shipments.operator.{uuid4()}",
        display_name="网点管理员",
        password_hash=hash_password("password"),
        role=Role.STATION_OPERATOR,
    )
    destination_operator = User(
        login_name=f"shipments.destination-operator.{uuid4()}",
        display_name="目的网点管理员",
        password_hash=hash_password("password"),
        role=Role.STATION_OPERATOR,
    )
    pickup_courier = User(
        login_name=f"shipments.pickup.{uuid4()}",
        display_name="取件快递员",
        password_hash=hash_password("password"),
        role=Role.COURIER,
    )
    delivery_courier = User(
        login_name=f"shipments.delivery.{uuid4()}",
        display_name="派送快递员",
        password_hash=hash_password("password"),
        role=Role.COURIER,
    )
    operations = User(
        login_name=f"shipments.operations.{uuid4()}",
        display_name="运营人员",
        password_hash=hash_password("password"),
        role=Role.OPERATIONS_ADMIN,
    )
    async with SessionFactory() as session, session.begin():
        session.add_all([station, destination_station])
        await session.flush()
        operator.station_id = station.id
        destination_operator.station_id = destination_station.id
        pickup_courier.station_id = station.id
        delivery_courier.station_id = destination_station.id
        session.add_all([owner, operator, destination_operator, pickup_courier, delivery_courier, operations])
        await session.flush()
        shipment = _shipment(owner.id, f"YT-DETAIL-{uuid4().hex[:8].upper()}", ShipmentStatus.PENDING_PAYMENT)
        shipment.origin_station_id = station.id
        shipment.destination_station_id = destination_station.id
        session.add(shipment)
        await session.flush()
        shipment_id = shipment.id
        session.add_all([
            CourierTask(
                shipment_id=shipment_id,
                station_id=station.id,
                task_type=CourierTaskType.PICKUP,
                status=CourierTaskStatus.ACCEPTED,
                assignee_id=pickup_courier.id,
            ),
            CourierTask(
                shipment_id=shipment_id,
                station_id=destination_station.id,
                task_type=CourierTaskType.DELIVERY,
                status=CourierTaskStatus.ACCEPTED,
                assignee_id=delivery_courier.id,
            ),
        ])

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        actors = [
            (owner, Role.CUSTOMER, None),
            (operator, Role.STATION_OPERATOR, station.id),
            (destination_operator, Role.STATION_OPERATOR, destination_station.id),
            (pickup_courier, Role.COURIER, station.id),
            (delivery_courier, Role.COURIER, destination_station.id),
            (operations, Role.OPERATIONS_ADMIN, None),
        ]
        for actor, role, station_id in actors:
            response = await client.get(
                f"/api/v1/shipments/{shipment_id}",
                headers=_headers(actor.id, role, station_id),
            )
            assert response.status_code == 200, response.text
            assert response.json()["shipment"]["id"] == str(shipment_id)
