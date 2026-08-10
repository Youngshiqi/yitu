from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from yitu.demo.seed import seed_demo_users
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.sla.models import SLARule
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
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        customer = next(user for user in users if user.demo_key == "customer")
        shipment = Shipment(
            shipment_no=f"SLA-{uuid4().hex[:20]}", owner_id=customer.id,
            pickup_method=PickupMethod.DOOR_PICKUP, delivery_method=DeliveryMethod.HOME_DELIVERY,
            status=ShipmentStatus.PENDING_PICKUP,
        )
        rule = SLARule(
            version=f"sla-{uuid4()}", route_code="TEST", service_type="STANDARD", stage="DELIVERY",
            target_natural_hours=1, effective_from=start_at - timedelta(days=1),
        )
        session.add_all([shipment, rule])
        await session.flush()
        service = SLAService(session, clock=clock)
        instance = await service.start(shipment.id, "TEST", "DELIVERY")
        frozen_promise = instance.promised_delivery_at
        await service.update_eta(instance.id, timedelta(minutes=20))
        assert instance.promised_delivery_at == frozen_promise
        assert instance.eta_at == frozen_promise + timedelta(minutes=20)

        clock.value = start_at + timedelta(hours=2)
        assert len(await service.scan_breaches("window-1")) == 1
        assert len(await service.scan_breaches("window-1")) == 0
