import asyncio
from uuid import uuid4

import pytest

from tests.dispatch.test_pickup import _shipment
from yitu.dispatch.service import DispatchService
from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import PickupMethod
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
