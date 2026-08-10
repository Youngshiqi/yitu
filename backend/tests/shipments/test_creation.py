from uuid import uuid4

import pytest

from yitu.addresses.models import Address
from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.schemas import CreateShipmentCommand, ShipmentDraft

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> None:
    """每个测试前清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()


async def _customer_with_addresses() -> tuple[CurrentUser, Address, Address]:
    owner_id = uuid4()
    user = User(
        id=owner_id,
        login_name=f"shipment.{owner_id}",
        display_name="运单测试客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    async with SessionFactory() as session, session.begin():
        session.add(user)
        await session.flush()
        sender = Address(owner_id=owner_id, recipient_name="寄件人", phone="13800000000", district_code="310105", detail="虹桥路1号")
        receiver = Address(owner_id=owner_id, recipient_name="收件人", phone="13900000000", district_code="440106", detail="天河路2号")
        session.add_all([sender, receiver])
    return CurrentUser(id=owner_id, role=Role.CUSTOMER, station_id=None), sender, receiver


def _command(sender: Address, receiver: Address) -> CreateShipmentCommand:
    return CreateShipmentCommand(
        draft=ShipmentDraft(
            sender_address_id=sender.id,
            receiver_address_id=receiver.id,
            pickup_method=PickupMethod.DOOR_PICKUP,
            delivery_method=DeliveryMethod.HOME_DELIVERY,
        )
    )


async def test_create_shipment_requires_customer_owned_addresses() -> None:
    from yitu.shipments.service import ShipmentApplicationService

    _actor, sender, receiver = await _customer_with_addresses()
    other_actor = CurrentUser(id=uuid4(), role=Role.CUSTOMER, station_id=None)
    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError, match="只能访问本人资源"):
            await ShipmentApplicationService(session).create(_command(sender, receiver), other_actor, "other-owner")


async def test_create_shipment_replays_same_idempotency_key() -> None:
    from yitu.shipments.service import ShipmentApplicationService

    actor, sender, receiver = await _customer_with_addresses()
    async with SessionFactory() as session, session.begin():
        service = ShipmentApplicationService(session)
        first = await service.create(_command(sender, receiver), actor, "create-same")
    async with SessionFactory() as session, session.begin():
        replay = await ShipmentApplicationService(session).create(_command(sender, receiver), actor, "create-same")
    assert replay == first
    assert first.status is ShipmentStatus.PENDING_PAYMENT
    assert first.shipment_no.startswith("YT")


async def test_create_shipment_rejects_conflicting_idempotency_request() -> None:
    from yitu.shipments.service import ShipmentApplicationService

    actor, sender, receiver = await _customer_with_addresses()
    async with SessionFactory() as session, session.begin():
        await ShipmentApplicationService(session).create(_command(sender, receiver), actor, "create-conflict")
    changed = CreateShipmentCommand(
        draft=_command(sender, receiver).draft.model_copy(update={"delivery_method": DeliveryMethod.STATION_PICKUP, "destination_station_id": uuid4()})
    )
    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError, match="幂等键"):
            await ShipmentApplicationService(session).create(changed, actor, "create-conflict")
