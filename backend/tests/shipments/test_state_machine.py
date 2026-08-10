from uuid import uuid4

import pytest

from yitu.addresses.models import Address
from yitu.identity.models import Role, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import ShipmentStatus


@pytest.fixture(autouse=True)
async def reset_database_pool() -> None:
    """每个测试前清理连接池，避免跨事件循环复用旧连接。"""
    await dispose_database()


def test_state_machine_allows_initial_payment_transition() -> None:
    from yitu.shipments.state_machine import allowed_actions, transition

    assert transition(ShipmentStatus.PENDING_PAYMENT, ShipmentStatus.PENDING_PICKUP) is ShipmentStatus.PENDING_PICKUP
    assert "confirm_payment" in allowed_actions(ShipmentStatus.PENDING_PAYMENT)


def test_state_machine_rejects_skipped_transition() -> None:
    from yitu.shipments.state_machine import transition

    with pytest.raises(AppError, match="不允许"):
        transition(ShipmentStatus.PENDING_PAYMENT, ShipmentStatus.DELIVERED)


async def _shipment() -> tuple[CurrentUser, object]:
    from yitu.shipments.models import Shipment

    user_id = uuid4()
    user = User(id=user_id, login_name=f"state.{user_id}", display_name="状态测试客户", password_hash=hash_password("密码"), role=Role.CUSTOMER)
    async with SessionFactory() as session, session.begin():
        session.add(user)
        await session.flush()
        address = Address(owner_id=user_id, recipient_name="寄件人", phone="13800000000", district_code="310105", detail="虹桥路1号")
        session.add(address)
        await session.flush()
        shipment = Shipment(shipment_no=f"YT{uuid4().hex[:16].upper()}", owner_id=user_id, sender_address_id=address.id, receiver_address_id=address.id, pickup_method="DOOR_PICKUP", delivery_method="HOME_DELIVERY", status=ShipmentStatus.PENDING_PAYMENT)
        session.add(shipment)
        await session.flush()
        shipment_id = shipment.id
    return CurrentUser(id=user_id, role=Role.CUSTOMER, station_id=None), shipment_id


@pytest.mark.asyncio(loop_scope="function")
async def test_transition_appends_ordered_tracking_and_deduplicates_event() -> None:
    from yitu.shipments.service import ShipmentTransitionService
    from yitu.tracking.service import list_tracking_events

    actor, shipment_id = await _shipment()
    async with SessionFactory() as session, session.begin():
        shipment = await session.get(__import__("yitu.shipments.models", fromlist=["Shipment"]).Shipment, shipment_id)
        assert shipment is not None
        service = ShipmentTransitionService(session)
        await service.transition(shipment, ShipmentStatus.PENDING_PICKUP, actor, "confirm_payment", "request-1")
        await service.transition(shipment, ShipmentStatus.PENDING_PICKUP, actor, "confirm_payment", "request-1")
        events = await list_tracking_events(session, shipment_id)
    assert len(events) == 1
    assert events[0].sequence_no == 1
    assert events[0].visible_to_customer is True
