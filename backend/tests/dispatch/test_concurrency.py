import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.dispatch.test_pickup import _shipment
from yitu.dispatch.service import DispatchService
from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import PickupMethod, ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool():
    """在测试前后清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()
    yield
    await dispose_database()


async def test_concurrent_couriers_only_one_can_accept_task() -> None:
    shipment_id, station_id, first_courier, _operator = await _shipment(PickupMethod.DOOR_PICKUP)
    second_courier_id = uuid4()
    async with SessionFactory() as session, session.begin():
        session.add(User(id=second_courier_id, login_name=f"courier.{second_courier_id}", display_name="第二揽收员", password_hash=hash_password("密码"), role=Role.COURIER, station_id=station_id))
        shipment = await session.get(Shipment, shipment_id)
        assert shipment is not None
        task = await DispatchService(session).create_pickup_task(shipment, station_id)
        task_id = task.id
    second_courier = CurrentUser(id=second_courier_id, role=Role.COURIER, station_id=station_id)

    async def compete(actor: CurrentUser, request_id: str) -> str:
        try:
            async with SessionFactory() as session, session.begin():
                await DispatchService(session).accept_task(task_id, actor, request_id)
            return "accepted"
        except AppError as error:
            return error.code

    results = await asyncio.gather(
        compete(first_courier, "accept-first"),
        compete(second_courier, "accept-second"),
    )
    assert sorted(results) == ["TASK_ALREADY_ASSIGNED", "accepted"]


async def test_concurrent_hold_and_task_acceptance_are_serialized() -> None:
    from yitu.shipments.control import ShipmentControlService

    shipment_id, station_id, courier, _operator = await _shipment(PickupMethod.DOOR_PICKUP)
    source_id = uuid4()
    async with SessionFactory() as session, session.begin():
        shipment = await session.get(Shipment, shipment_id)
        assert shipment is not None
        task = await DispatchService(session).create_pickup_task(shipment, station_id)
        task_id = task.id

    async def accept_task() -> str:
        try:
            async with SessionFactory() as session, session.begin():
                await DispatchService(session).accept_task(task_id, courier, "accept-vs-hold")
            return "accepted"
        except AppError as error:
            return error.code

    async def place_hold() -> str:
        async with SessionFactory() as session, session.begin():
            await ShipmentControlService(session).place_exception_hold(
                shipment_id=shipment_id,
                source_type="EXCEPTION_CASE",
                source_id=source_id,
                reason="并发异常冻结",
                actor=courier,
                idempotency_key=f"hold:{source_id}",
            )
        return "held"

    results = await asyncio.gather(accept_task(), place_hold())

    async with SessionFactory() as session:
        shipment = await session.get(Shipment, shipment_id)
        active_hold = await session.scalar(
            select(ShipmentHold).where(
                ShipmentHold.source_type == "EXCEPTION_CASE",
                ShipmentHold.source_id == source_id,
            )
        )

    assert shipment is not None
    assert active_hold is not None
    assert sorted(results) in [
        ["SHIPMENT_FULFILLMENT_BLOCKED", "held"],
        ["accepted", "held"],
    ]
    if "accepted" in results:
        assert shipment.status == ShipmentStatus.PICKUP_ASSIGNED
        assert active_hold.frozen_status == ShipmentStatus.PICKUP_ASSIGNED
    else:
        assert shipment.status == ShipmentStatus.PENDING_PICKUP
        assert active_hold.frozen_status == ShipmentStatus.PENDING_PICKUP
