from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    """在测试前后清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()
    yield
    await dispose_database()


async def _shipment(delivery_method: DeliveryMethod) -> tuple[CurrentUser, CurrentUser, UUID, UUID, UUID]:
    origin = Station(id=uuid4(), code=f"OR-{uuid4().hex[:8]}", name="始发网点", district_code="110101")
    destination = Station(id=uuid4(), code=f"DE-{uuid4().hex[:8]}", name="目标网点", district_code="310105")
    customer_id, operator_id, admin_id = uuid4(), uuid4(), uuid4()
    users = [
        User(id=customer_id, login_name=f"line.customer.{customer_id}", display_name="客户", password_hash=hash_password("密码"), role=Role.CUSTOMER),
        User(id=operator_id, login_name=f"line.operator.{operator_id}", display_name="网点员", password_hash=hash_password("密码"), role=Role.STATION_OPERATOR, station_id=origin.id),
        User(id=admin_id, login_name=f"line.admin.{admin_id}", display_name="运营", password_hash=hash_password("密码"), role=Role.OPERATIONS_ADMIN),
    ]
    shipment = Shipment(id=uuid4(), shipment_no=f"YT{uuid4().hex[:16].upper()}", owner_id=customer_id, origin_station_id=origin.id, destination_station_id=destination.id, pickup_method=PickupMethod.STATION_DROPOFF, delivery_method=delivery_method, status=ShipmentStatus.AT_ORIGIN_STATION)
    async with SessionFactory() as session, session.begin():
        session.add_all([origin, destination])
        await session.flush()
        session.add_all(users)
        await session.flush()
        session.add(shipment)
    return CurrentUser(id=operator_id, role=Role.STATION_OPERATOR, station_id=origin.id), CurrentUser(id=admin_id, role=Role.OPERATIONS_ADMIN, station_id=None), shipment.id, origin.id, destination.id


async def test_linehaul_dispatch_and_arrival_create_delivery_task() -> None:
    from yitu.shipments.linehaul import LinehaulService

    operator, admin, shipment_id, _origin_id, _destination_id = await _shipment(DeliveryMethod.HOME_DELIVERY)
    async with SessionFactory() as session, session.begin():
        service = LinehaulService(session)
        await service.dispatch_linehaul(shipment_id, operator, "dispatch-1")
        result = await service.arrive_destination(shipment_id, admin, "arrive-1")
        tasks = list((await session.scalars(select(CourierTask).where(CourierTask.shipment_id == shipment_id))).all())
    assert result.status is ShipmentStatus.AT_DESTINATION_STATION
    assert result.next_action == "CREATE_DELIVERY_TASK"
    assert len(tasks) == 1
    assert CourierTaskType(tasks[0].task_type) is CourierTaskType.DELIVERY
    assert CourierTaskStatus(tasks[0].status) is CourierTaskStatus.AVAILABLE


async def test_station_pickup_arrival_requests_credential_without_delivery_task() -> None:
    from yitu.shipments.linehaul import LinehaulService

    operator, admin, shipment_id, _origin_id, _destination_id = await _shipment(DeliveryMethod.STATION_PICKUP)
    async with SessionFactory() as session, session.begin():
        service = LinehaulService(session)
        await service.dispatch_linehaul(shipment_id, operator, "dispatch-2")
        result = await service.arrive_destination(shipment_id, admin, "arrive-2")
        tasks = list((await session.scalars(select(CourierTask).where(CourierTask.shipment_id == shipment_id))).all())
    assert result.next_action == "ISSUE_PICKUP_CREDENTIAL"
    assert len(tasks) == 0


async def test_arrival_before_dispatch_is_rejected() -> None:
    from yitu.shipments.linehaul import LinehaulService

    operator, admin, shipment_id, _origin_id, _destination_id = await _shipment(DeliveryMethod.HOME_DELIVERY)
    del operator
    async with SessionFactory() as session, session.begin():
        service = LinehaulService(session)
        with pytest.raises(AppError, match="不允许"):
            await service.arrive_destination(shipment_id, admin, "arrive-too-early")
