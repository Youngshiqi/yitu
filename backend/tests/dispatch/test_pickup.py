from uuid import uuid4

import pytest

from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    """在测试前后清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()
    yield
    await dispose_database()


async def _shipment(pickup_method: PickupMethod):
    from yitu.shipments.models import Shipment

    station = Station(id=uuid4(), code=f"TS-{uuid4().hex[:8]}", name="测试网点", district_code="310105")
    customer_id = uuid4()
    courier_id = uuid4()
    operator_id = uuid4()
    users = [
        User(id=customer_id, login_name=f"customer.{customer_id}", display_name="客户", password_hash=hash_password("密码"), role=Role.CUSTOMER),
        User(id=courier_id, login_name=f"courier.{courier_id}", display_name="揽收员", password_hash=hash_password("密码"), role=Role.COURIER, station_id=station.id),
        User(id=operator_id, login_name=f"operator.{operator_id}", display_name="网点员", password_hash=hash_password("密码"), role=Role.STATION_OPERATOR, station_id=station.id),
    ]
    shipment = Shipment(shipment_no=f"YT{uuid4().hex[:16].upper()}", owner_id=customer_id, sender_address_id=None, receiver_address_id=None, origin_station_id=station.id, destination_station_id=None, pickup_method=pickup_method, delivery_method=DeliveryMethod.HOME_DELIVERY, status=ShipmentStatus.PENDING_PICKUP if pickup_method is PickupMethod.DOOR_PICKUP else ShipmentStatus.WAITING_FOR_DROPOFF)
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all(users)
        await session.flush()
        session.add(shipment)
        await session.flush()
        shipment_id = shipment.id
    return shipment_id, station.id, CurrentUser(id=courier_id, role=Role.COURIER, station_id=station.id), CurrentUser(id=operator_id, role=Role.STATION_OPERATOR, station_id=station.id)


async def test_door_pickup_creates_task_then_reaches_origin_station() -> None:
    from yitu.dispatch.service import DispatchService
    from yitu.shipments.models import Shipment

    shipment_id, station_id, courier, operator = await _shipment(PickupMethod.DOOR_PICKUP)
    async with SessionFactory() as session, session.begin():
        shipment = await session.get(Shipment, shipment_id)
        assert shipment is not None
        service = DispatchService(session)
        task = await service.create_pickup_task(shipment, station_id)
        await service.accept_task(task.id, courier, "accept-1")
        await service.confirm_pickup(task.id, courier, "pickup-1")
        result = await service.confirm_origin_arrival(shipment_id, operator, "arrival-1")
    assert result.status is ShipmentStatus.AT_ORIGIN_STATION


async def test_dropoff_creates_no_pickup_task_and_reaches_origin_station() -> None:
    from yitu.dispatch.service import DispatchService

    shipment_id, _station_id, _courier, operator = await _shipment(PickupMethod.STATION_DROPOFF)
    async with SessionFactory() as session, session.begin():
        service = DispatchService(session)
        result = await service.accept_dropoff(shipment_id, operator, "dropoff-1")
        tasks = await service.list_pickup_tasks(shipment_id)
    assert result.status is ShipmentStatus.AT_ORIGIN_STATION
    assert tasks == []


async def test_pickup_task_rejects_courier_from_another_station() -> None:
    from yitu.dispatch.service import DispatchService
    from yitu.platform.errors import AppError
    from yitu.shipments.models import Shipment

    shipment_id, station_id, _courier, _operator = await _shipment(PickupMethod.DOOR_PICKUP)
    wrong_courier = CurrentUser(id=uuid4(), role=Role.COURIER, station_id=uuid4())
    async with SessionFactory() as session, session.begin():
        shipment = await session.get(Shipment, shipment_id)
        assert shipment is not None
        task = await DispatchService(session).create_pickup_task(shipment, station_id)
        with pytest.raises(AppError, match="网点范围"):
            await DispatchService(session).accept_task(task.id, wrong_courier, "accept-wrong")
