from collections.abc import AsyncIterator
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.payments.schemas import PayRequest
from yitu.payments.service import PaymentService
from yitu.platform.database import SessionFactory, dispose_database
from yitu.pricing.models import PricingRule, QuoteSnapshot
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def test_payment_creates_available_pickup_task_for_origin_station() -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    station = Station(code=f"PAY-{uuid4().hex[:8]}", name="支付测试网点", district_code="310105")
    customer = User(
        login_name=f"payment.customer.{uuid4()}",
        display_name="支付测试客户",
        password_hash=hash_password("password"),
        role=Role.CUSTOMER,
    )
    rule = PricingRule(
        version=f"payment-rule-{uuid4()}",
        route_code="TEST",
        base_fee_cents=1000,
        additional_fee_cents=0,
        effective_from=now,
    )
    async with SessionFactory() as session, session.begin():
        session.add_all([station, customer, rule])
        await session.flush()
        quote = QuoteSnapshot(
            owner_id=customer.id,
            rule_id=rule.id,
            rule_version=rule.version,
            input_snapshot={"route_code": "TEST"},
            fee_items=[{"code": "BASE", "amount_cents": 1000}],
            volume_weight_grams=1000,
            billable_weight_grams=1000,
            total_cents=1000,
            created_at=now,
        )
        session.add(quote)
        await session.flush()
        shipment = Shipment(
            shipment_no=f"YT{uuid4().hex[:16].upper()}",
            owner_id=customer.id,
            origin_station_id=station.id,
            destination_station_id=station.id,
            pickup_method=PickupMethod.DOOR_PICKUP,
            delivery_method=DeliveryMethod.HOME_DELIVERY,
            status=ShipmentStatus.PENDING_PAYMENT,
            quote_id=quote.id,
        )
        session.add(shipment)
        await session.flush()
        shipment_id = shipment.id
        quote_id = quote.id
        station_id = station.id
        actor = CurrentUser(id=customer.id, role=Role.CUSTOMER, station_id=None)

    async with SessionFactory() as session, session.begin():
        await PaymentService(session).pay_quote(
            quote_id,
            PayRequest(shipment_id=shipment_id, amount_cents=1000),
            actor,
            f"payment:{uuid4()}",
        )
        tasks = list(
            (
                await session.scalars(
                    select(CourierTask).where(CourierTask.shipment_id == shipment_id)
                )
            ).all()
        )

    assert len(tasks) == 1
    assert tasks[0].station_id == station_id
    assert CourierTaskType(tasks[0].task_type) is CourierTaskType.PICKUP
    assert CourierTaskStatus(tasks[0].status) is CourierTaskStatus.AVAILABLE
