from datetime import timedelta
from uuid import uuid4

import pytest

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
    await dispose_database()
    yield
    await dispose_database()


async def _arrival(delivery_method: DeliveryMethod):
    station = Station(id=uuid4(), code=f"LM-{uuid4().hex[:8]}", name="末端网点", district_code="310105")
    ids = [uuid4() for _ in range(3)]
    customer_id, courier_id, operator_id = ids
    users = [
        User(id=customer_id, login_name=f"lm.customer.{customer_id}", display_name="客户", password_hash=hash_password("密码"), role=Role.CUSTOMER),
        User(id=courier_id, login_name=f"lm.courier.{courier_id}", display_name="派送员", password_hash=hash_password("密码"), role=Role.COURIER, station_id=station.id),
        User(id=operator_id, login_name=f"lm.operator.{operator_id}", display_name="网点员", password_hash=hash_password("密码"), role=Role.STATION_OPERATOR, station_id=station.id),
    ]
    shipment = Shipment(id=uuid4(), shipment_no=f"YT{uuid4().hex[:16].upper()}", owner_id=customer_id, origin_station_id=station.id, destination_station_id=station.id, pickup_method=PickupMethod.STATION_DROPOFF, delivery_method=delivery_method, status=ShipmentStatus.DELIVERY_ASSIGNED if delivery_method is DeliveryMethod.HOME_DELIVERY else ShipmentStatus.AT_DESTINATION_STATION)
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all(users)
        await session.flush()
        session.add(shipment)
        await session.flush()
        if delivery_method is DeliveryMethod.HOME_DELIVERY:
            session.add(CourierTask(shipment_id=shipment.id, station_id=station.id, task_type=CourierTaskType.DELIVERY, status=CourierTaskStatus.ACCEPTED, assignee_id=courier_id))
    return shipment.id, CurrentUser(id=courier_id, role=Role.COURIER, station_id=station.id), CurrentUser(id=operator_id, role=Role.STATION_OPERATOR, station_id=station.id)


async def test_delivery_requires_task_owner_and_creates_one_proof() -> None:
    from yitu.shipments.credentials import LastMileService

    shipment_id, courier, _operator = await _arrival(DeliveryMethod.HOME_DELIVERY)
    async with SessionFactory() as session, session.begin():
        service = LastMileService(session)
        await service.start_delivery(shipment_id, courier, "start-1")
        proof = await service.confirm_delivery(shipment_id, courier, "李四", "delivery-1")
        replay = await service.confirm_delivery(shipment_id, courier, "李四", "delivery-1")
    assert proof.id == replay.id
    assert proof.delivery_method is DeliveryMethod.HOME_DELIVERY


async def test_pickup_code_is_hashed_and_locks_after_five_failures() -> None:
    from yitu.shipments.credentials import LastMileService

    shipment_id, _courier, operator = await _arrival(DeliveryMethod.STATION_PICKUP)
    async with SessionFactory() as session, session.begin():
        credential = await LastMileService(session).issue_pickup_credential(shipment_id, operator, "issue-1", code="123456")
        assert credential.code_hash != "123456"
        for attempt in range(5):
            with pytest.raises(AppError):
                await LastMileService(session).verify_station_pickup(shipment_id, operator, "000000", f"wrong-{attempt}")
        assert credential.locked_at is not None


async def test_expired_pickup_code_can_be_reissued_and_consumed_idempotently() -> None:
    from yitu.shipments.credentials import LastMileService

    shipment_id, _courier, operator = await _arrival(DeliveryMethod.STATION_PICKUP)
    async with SessionFactory() as session, session.begin():
        service = LastMileService(session)
        await service.issue_pickup_credential(shipment_id, operator, "issue-old", code="111111", expires_in=timedelta(seconds=-1))
        credential = await service.reissue_pickup_credential(shipment_id, operator, "reissue-1", code="222222")
        proof = await service.verify_station_pickup(shipment_id, operator, "222222", "pickup-1")
        replay = await service.verify_station_pickup(shipment_id, operator, "222222", "pickup-1")
    assert credential.code_hash != "222222"
    assert proof.id == replay.id
    assert proof.delivery_method is DeliveryMethod.STATION_PICKUP
