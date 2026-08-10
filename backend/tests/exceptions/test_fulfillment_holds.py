from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.dispatch.service import DispatchService
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.payments.schemas import PayRequest
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.pricing.models import PricingRule, QuoteSnapshot
from yitu.shipments.credentials import LastMileService
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.linehaul import LinehaulService
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_shipment(
    *,
    status: ShipmentStatus,
    pickup_method: PickupMethod = PickupMethod.DOOR_PICKUP,
    delivery_method: DeliveryMethod = DeliveryMethod.HOME_DELIVERY,
) -> tuple[Shipment, Station, CurrentUser, CurrentUser, CurrentUser, User]:
    station = Station(
        id=uuid4(),
        code=f"HOLD-{uuid4().hex[:8]}",
        name="异常冻结测试网点",
        district_code="310105",
    )
    customer = User(
        id=uuid4(),
        login_name=f"hold.customer.{uuid4()}",
        display_name="冻结客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    courier = User(
        id=uuid4(),
        login_name=f"hold.courier.{uuid4()}",
        display_name="冻结快递员",
        password_hash=hash_password("密码"),
        role=Role.COURIER,
        station_id=station.id,
    )
    operator = User(
        id=uuid4(),
        login_name=f"hold.operator.{uuid4()}",
        display_name="冻结网点员",
        password_hash=hash_password("密码"),
        role=Role.STATION_OPERATOR,
        station_id=station.id,
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=pickup_method,
        delivery_method=delivery_method,
        status=status,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all([customer, courier, operator])
        await session.flush()
        session.add(shipment)
    return (
        shipment,
        station,
        CurrentUser(id=customer.id, role=Role.CUSTOMER, station_id=None),
        CurrentUser(id=courier.id, role=Role.COURIER, station_id=station.id),
        CurrentUser(id=operator.id, role=Role.STATION_OPERATOR, station_id=station.id),
        customer,
    )


async def _place_hold(
    shipment_id: UUID,
    actor: CurrentUser,
    source_id: UUID | None = None,
) -> UUID:
    from yitu.shipments.control import ShipmentControlService

    hold_source_id = source_id or uuid4()
    async with SessionFactory() as session, session.begin():
        hold = await ShipmentControlService(session).place_exception_hold(
            shipment_id=shipment_id,
            source_type="EXCEPTION_CASE",
            source_id=hold_source_id,
            reason="异常处理中，暂停履约推进",
            actor=actor,
            idempotency_key=f"hold:{hold_source_id}",
        )
    assert hold.source_id == hold_source_id
    return hold_source_id


async def test_hold_creation_is_idempotent_and_release_restores_fulfillment() -> None:
    from yitu.shipments.control import ShipmentControlService
    from yitu.shipments.hold_models import ShipmentHold

    shipment, _station, customer, courier, _operator, _customer_model = await _seed_shipment(
        status=ShipmentStatus.PENDING_PICKUP
    )
    source_id = uuid4()
    async with SessionFactory() as session, session.begin():
        service = ShipmentControlService(session)
        first = await service.place_exception_hold(
            shipment_id=shipment.id,
            source_type="EXCEPTION_CASE",
            source_id=source_id,
            reason="地址异常",
            actor=customer,
            idempotency_key="hold:create:first",
        )
        replay = await service.place_exception_hold(
            shipment_id=shipment.id,
            source_type="EXCEPTION_CASE",
            source_id=source_id,
            reason="地址异常",
            actor=customer,
            idempotency_key="hold:create:first",
        )

    assert replay.id == first.id
    assert first.frozen_status == ShipmentStatus.PENDING_PICKUP

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as blocked:
            await ShipmentControlService(session).lock_and_assert_fulfillment_allowed(shipment.id)
        await ShipmentControlService(session).release_exception_holds(
            shipment_id=shipment.id,
            source_type="EXCEPTION_CASE",
            source_ids=[source_id],
            actor=courier,
            idempotency_key="hold:release:first",
        )
        allowed = await ShipmentControlService(session).lock_and_assert_fulfillment_allowed(shipment.id)
        saved = await session.get(ShipmentHold, first.id)

    assert blocked.value.code == "SHIPMENT_FULFILLMENT_BLOCKED"
    assert allowed.id == shipment.id
    assert saved is not None
    assert saved.active is False
    assert saved.released_by == courier.id
    assert saved.release_idempotency_key == "hold:release:first"


async def test_active_hold_blocks_pickup_task_acceptance() -> None:
    shipment, station, _customer, courier, _operator, _customer_model = await _seed_shipment(
        status=ShipmentStatus.PENDING_PICKUP
    )
    async with SessionFactory() as session, session.begin():
        stored = await session.get(Shipment, shipment.id)
        assert stored is not None
        task = await DispatchService(session).create_pickup_task(stored, station.id)
    await _place_hold(shipment.id, courier)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as blocked:
            await DispatchService(session).accept_task(task.id, courier, "accept-blocked")

    assert blocked.value.code == "SHIPMENT_FULFILLMENT_BLOCKED"


async def test_active_hold_blocks_linehaul_dispatch() -> None:
    shipment, _station, _customer, _courier, operator, _customer_model = await _seed_shipment(
        status=ShipmentStatus.AT_ORIGIN_STATION,
        pickup_method=PickupMethod.STATION_DROPOFF,
    )
    await _place_hold(shipment.id, operator)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as blocked:
            await LinehaulService(session).dispatch_linehaul(
                shipment.id,
                operator,
                "linehaul-blocked",
            )

    assert blocked.value.code == "SHIPMENT_FULFILLMENT_BLOCKED"


async def test_active_hold_blocks_last_mile_delivery_start() -> None:
    shipment, station, _customer, courier, _operator, _customer_model = await _seed_shipment(
        status=ShipmentStatus.DELIVERY_ASSIGNED
    )
    async with SessionFactory() as session, session.begin():
        session.add(
            CourierTask(
                shipment_id=shipment.id,
                station_id=station.id,
                task_type=CourierTaskType.DELIVERY,
                status=CourierTaskStatus.ACCEPTED,
                assignee_id=courier.id,
            )
        )
    await _place_hold(shipment.id, courier)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as blocked:
            await LastMileService(session).start_delivery(
                shipment.id,
                courier,
                "delivery-blocked",
            )

    assert blocked.value.code == "SHIPMENT_FULFILLMENT_BLOCKED"


async def test_active_hold_blocks_payment_status_advancement() -> None:
    from yitu.payments.service import PaymentService

    shipment, _station, customer, _courier, _operator, customer_model = await _seed_shipment(
        status=ShipmentStatus.PENDING_PAYMENT
    )
    rule = PricingRule(
        version=f"hold-price-{uuid4()}",
        route_code="TEST",
        base_fee_cents=1000,
        additional_fee_cents=0,
        remote_surcharge_cents=0,
        effective_from=datetime(2026, 8, 10, 8, 0, tzinfo=TZ),
    )
    async with SessionFactory() as session, session.begin():
        session.add(rule)
        await session.flush()
        quote = QuoteSnapshot(
            owner_id=customer_model.id,
            rule_id=rule.id,
            rule_version=rule.version,
            input_snapshot={"route_code": "TEST"},
            fee_items=[{"code": "BASE", "amount_cents": 1000}],
            volume_weight_grams=1000,
            billable_weight_grams=1000,
            total_cents=1000,
            created_at=datetime(2026, 8, 10, 8, 5, tzinfo=TZ),
        )
        session.add(quote)
        await session.flush()
        quote_id = quote.id
    await _place_hold(shipment.id, customer)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as blocked:
            await PaymentService(session).pay_quote(
                quote_id,
                PayRequest(shipment_id=shipment.id, amount_cents=1000),
                customer,
                f"payment:{uuid4()}",
            )

    assert blocked.value.code == "SHIPMENT_FULFILLMENT_BLOCKED"
