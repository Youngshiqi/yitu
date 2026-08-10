from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from yitu.demo.seed import seed_demo_users
from yitu.exceptions.enums import ExceptionSourceType, ExceptionStatus, ExceptionType
from yitu.exceptions.models import ExceptionCase
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.sla.models import SLAPause, SLARule
from yitu.sla.service import SLAService

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    """避免不同测试事件循环复用 asyncpg 连接。"""
    await dispose_database()
    yield
    await dispose_database()


class FixedClock:
    """为 SLA 生命周期测试提供固定时间。"""

    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


async def test_eta_does_not_overwrite_promise_and_scan_is_idempotent() -> None:
    start_at = datetime(2026, 8, 14, 10, tzinfo=TZ)
    clock = FixedClock(start_at)
    route_code = f"TEST-{uuid4()}"
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        customer = next(user for user in users if user.demo_key == "customer")
        shipment = Shipment(
            shipment_no=f"SLA-{uuid4().hex[:20]}", owner_id=customer.id,
            pickup_method=PickupMethod.DOOR_PICKUP, delivery_method=DeliveryMethod.HOME_DELIVERY,
            status=ShipmentStatus.PENDING_PICKUP,
        )
        rule = SLARule(
            version=f"sla-{uuid4()}", route_code=route_code, service_type="STANDARD", stage="DELIVERY",
            target_natural_hours=1, effective_from=start_at - timedelta(days=1),
        )
        session.add_all([shipment, rule])
        await session.flush()
        service = SLAService(session, clock=clock)
        instance = await service.start(shipment.id, route_code, "DELIVERY")
        frozen_promise = instance.promised_delivery_at
        await service.update_eta(instance.id, timedelta(minutes=20))
        assert instance.promised_delivery_at == frozen_promise
        assert instance.eta_at == frozen_promise + timedelta(minutes=20)

        clock.value = start_at + timedelta(hours=2)
        changed = await service.scan_breaches("window-1")
        assert instance.id in {item.id for item in changed}
        assert len(await service.scan_breaches("window-1")) == 0


async def test_scan_breaches_opens_station_delay_case_once() -> None:
    start_at = datetime(2026, 8, 14, 10, tzinfo=TZ)
    clock = FixedClock(start_at)
    route_code = f"TEST-{uuid4()}"
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        customer = next(user for user in users if user.demo_key == "customer")
        shipment = Shipment(
            shipment_no=f"SLA-{uuid4().hex[:20]}",
            owner_id=customer.id,
            pickup_method=PickupMethod.DOOR_PICKUP,
            delivery_method=DeliveryMethod.HOME_DELIVERY,
            status=ShipmentStatus.PENDING_PICKUP,
        )
        rule = SLARule(
            version=f"sla-auto-{uuid4()}",
            route_code=route_code,
            service_type="STANDARD",
            stage="PICKUP",
            target_natural_hours=1,
            effective_from=start_at - timedelta(days=1),
        )
        session.add_all([shipment, rule])
        await session.flush()
        service = SLAService(session, clock=clock)
        instance = await service.start(shipment.id, route_code, "PICKUP")
        clock.value = start_at + timedelta(hours=2)
        changed = await service.scan_breaches("window-1")
        assert instance.id in {item.id for item in changed}
        assert len(await service.scan_breaches("window-2")) == 0

    async with SessionFactory() as session:
        cases = (
            await session.scalars(
                select(ExceptionCase).where(
                    ExceptionCase.source_type == ExceptionSourceType.SLA_SCAN,
                    ExceptionCase.source_id == instance.id,
                )
            )
        ).all()

    assert len(cases) == 1
    assert cases[0].case_type == ExceptionType.STATION_DELAY
    assert cases[0].status == ExceptionStatus.OPEN
    assert cases[0].blocks_fulfillment is False


async def test_pause_and_resume_for_source_only_affect_matching_pause() -> None:
    start_at = datetime(2026, 8, 14, 10, tzinfo=TZ)
    clock = FixedClock(start_at)
    route_code = f"TEST-{uuid4()}"
    first_source = uuid4()
    second_source = uuid4()
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        customer = next(user for user in users if user.demo_key == "customer")
        shipment = Shipment(
            shipment_no=f"SLA-{uuid4().hex[:20]}",
            owner_id=customer.id,
            pickup_method=PickupMethod.DOOR_PICKUP,
            delivery_method=DeliveryMethod.HOME_DELIVERY,
            status=ShipmentStatus.PENDING_PICKUP,
        )
        rule = SLARule(
            version=f"sla-source-{uuid4()}",
            route_code=route_code,
            service_type="STANDARD",
            stage="DELIVERY",
            target_natural_hours=4,
            effective_from=start_at - timedelta(days=1),
        )
        session.add_all([shipment, rule])
        await session.flush()
        service = SLAService(session, clock=clock)
        instance = await service.start(shipment.id, route_code, "DELIVERY")
        original_promise = instance.promised_delivery_at
        await service.pause_for_source(
            instance.id,
            reason="等待客户补充地址",
            reason_code="WAITING_FOR_ADDRESS",
            source_type="EXCEPTION_CASE",
            source_id=first_source,
            actor_id=customer.id,
            idempotency_key="pause:first",
        )
        replay = await service.pause_for_source(
            instance.id,
            reason="等待客户补充地址",
            reason_code="WAITING_FOR_ADDRESS",
            source_type="EXCEPTION_CASE",
            source_id=first_source,
            actor_id=customer.id,
            idempotency_key="pause:first",
        )
        await service.pause_for_source(
            instance.id,
            reason="等待客户补充信息",
            reason_code="WAITING_FOR_SUPPLEMENT",
            source_type="EXCEPTION_CASE",
            source_id=second_source,
            actor_id=customer.id,
            idempotency_key="pause:second",
        )

        clock.value = start_at + timedelta(minutes=30)
        await service.resume_for_source(
            instance.id,
            source_type="EXCEPTION_CASE",
            source_id=first_source,
            idempotency_key="resume:first",
        )
        assert replay.id == instance.id
        assert instance.status == "PAUSED"

        clock.value = start_at + timedelta(minutes=45)
        await service.resume_for_source(
            instance.id,
            source_type="EXCEPTION_CASE",
            source_id=second_source,
            idempotency_key="resume:second",
        )

    async with SessionFactory() as session:
        pauses = (
            await session.scalars(
                select(SLAPause).where(SLAPause.instance_id == instance.id)
            )
        ).all()

    assert instance.status == "RUNNING"
    assert instance.promised_delivery_at == original_promise + timedelta(minutes=75)
    assert len(pauses) == 2
    assert {pause.source_id for pause in pauses} == {first_source, second_source}
    assert all(pause.ended_at is not None for pause in pauses)
    assert {pause.pause_idempotency_key for pause in pauses} == {"pause:first", "pause:second"}
    assert {pause.resume_idempotency_key for pause in pauses} == {"resume:first", "resume:second"}
