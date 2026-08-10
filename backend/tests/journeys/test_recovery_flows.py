from collections.abc import AsyncIterator
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from tests.exceptions.test_api import _headers
from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.main import create_app
from yitu.payments.models import PaymentTransaction
from yitu.platform.database import SessionFactory, dispose_database
from yitu.pricing.models import PricingRule, QuoteSnapshot
from yitu.returns.models import RecoveryCase
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.sla.models import SLAInstance, SLARule

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_users() -> tuple[Station, User, User, User]:
    station = Station(
        id=uuid4(),
        code=f"RECOVERY-{uuid4().hex[:8]}",
        name="恢复流程网点",
        district_code="310105",
    )
    customer = User(
        id=uuid4(),
        login_name=f"recovery.customer.{uuid4()}",
        display_name="恢复流程客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    courier = User(
        id=uuid4(),
        login_name=f"recovery.courier.{uuid4()}",
        display_name="恢复流程快递员",
        password_hash=hash_password("密码"),
        role=Role.COURIER,
        station_id=station.id,
    )
    admin = User(
        id=uuid4(),
        login_name=f"recovery.admin.{uuid4()}",
        display_name="恢复流程运营",
        password_hash=hash_password("密码"),
        role=Role.OPERATIONS_ADMIN,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all([customer, courier, admin])
    return station, customer, courier, admin


async def _seed_paid_waiting_shipment(station: Station, customer: User) -> Shipment:
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        rule = PricingRule(
            version=f"recovery-price-{uuid4()}",
            route_code="TEST",
            base_fee_cents=1200,
            additional_fee_cents=0,
            remote_surcharge_cents=0,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        session.add(rule)
        await session.flush()
        sla_rule = SLARule(
            version=f"recovery-cancel-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="PICKUP",
            target_natural_hours=4,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        session.add(sla_rule)
        await session.flush()
        quote = QuoteSnapshot(
            owner_id=customer.id,
            rule_id=rule.id,
            rule_version=rule.version,
            input_snapshot={"route_code": "TEST"},
            fee_items=[{"code": "BASE", "amount_cents": 1200}],
            volume_weight_grams=1000,
            billable_weight_grams=1000,
            total_cents=1200,
            created_at=datetime(2026, 8, 10, 9, tzinfo=TZ),
        )
        session.add_all([shipment, quote])
        await session.flush()
        session.add(
            PaymentTransaction(
                owner_id=customer.id,
                quote_id=quote.id,
                shipment_id=shipment.id,
                transaction_type="PAYMENT",
                status="SUCCEEDED",
                amount_cents=1200,
                idempotency_key=f"paid:{shipment.id}",
                request_hash="paid",
                created_at=datetime(2026, 8, 10, 9, 5, tzinfo=TZ),
            )
        )
        session.add(
            SLAInstance(
                shipment_id=shipment.id,
                owner_id=customer.id,
                rule_id=sla_rule.id,
                rule_version=sla_rule.version,
                stage="PICKUP",
                status="RUNNING",
                started_at=datetime(2026, 8, 10, 9, 10, tzinfo=TZ),
                promised_delivery_at=datetime(2026, 8, 10, 13, 10, tzinfo=TZ),
            )
        )
    return shipment


async def _seed_delivery_shipment(station: Station, customer: User, courier: User) -> tuple[Shipment, CourierTask]:
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=PickupMethod.STATION_DROPOFF,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.OUT_FOR_DELIVERY,
    )
    task = CourierTask(
        shipment_id=shipment.id,
        station_id=station.id,
        task_type=CourierTaskType.DELIVERY,
        status=CourierTaskStatus.ACCEPTED,
        assignee_id=courier.id,
    )
    async with SessionFactory() as session, session.begin():
        delivery_rule = SLARule(
            version=f"recovery-delivery-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="DELIVERY",
            target_natural_hours=4,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        redelivery_rule = SLARule(
            version=f"recovery-redelivery-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="DELIVERY_REDELIVERY",
            target_natural_hours=4,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        pickup_rule = SLARule(
            version=f"recovery-pickup-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="PICKUP_AT_STATION",
            target_natural_hours=8,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        return_rule = SLARule(
            version=f"recovery-return-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="RETURN",
            target_natural_hours=24,
            effective_from=datetime(2026, 8, 10, 8, tzinfo=TZ),
        )
        session.add_all([delivery_rule, redelivery_rule, pickup_rule, return_rule])
        await session.flush()
        session.add(shipment)
        await session.flush()
        session.add(task)
        session.add(
            SLAInstance(
                shipment_id=shipment.id,
                owner_id=customer.id,
                rule_id=delivery_rule.id,
                rule_version=delivery_rule.version,
                stage="DELIVERY",
                status="RUNNING",
                started_at=datetime(2026, 8, 10, 9, tzinfo=TZ),
                promised_delivery_at=datetime(2026, 8, 10, 13, tzinfo=TZ),
            )
        )
        await session.flush()
    return shipment, task


async def test_paid_waiting_shipment_can_be_cancelled_with_refund_idempotently() -> None:
    station, customer, _courier, _admin = await _seed_users()
    shipment = await _seed_paid_waiting_shipment(station, customer)
    headers = _headers(customer.id, Role.CUSTOMER)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        first = await client.post(
            f"/api/v1/returns/shipments/{shipment.id}/cancel",
            headers={**headers, "Idempotency-Key": "cancel-paid"},
            json={"reason": "客户取消寄件"},
        )
        replay = await client.post(
            f"/api/v1/returns/shipments/{shipment.id}/cancel",
            headers={**headers, "Idempotency-Key": "cancel-paid"},
            json={"reason": "客户取消寄件"},
        )

    assert first.status_code == 200, first.text
    assert replay.json() == first.json()
    assert first.json()["shipment_status"] == "CANCELLED"
    assert first.json()["refund_amount_cents"] == 1200

    async with SessionFactory() as session:
        refund_count = await session.scalar(
            select(func.count())
            .select_from(PaymentTransaction)
            .where(
                PaymentTransaction.shipment_id == shipment.id,
                PaymentTransaction.transaction_type == "REFUND",
            )
        )
        active_sla_count = await session.scalar(
            select(func.count())
            .select_from(SLAInstance)
            .where(
                SLAInstance.shipment_id == shipment.id,
                SLAInstance.status.in_(["RUNNING", "PAUSED"]),
            )
        )
    assert refund_count == 1
    assert active_sla_count == 0


async def test_delivery_recovery_actions_cover_interception_redelivery_pickup_and_return() -> None:
    station, customer, courier, admin = await _seed_users()
    shipment, task = await _seed_delivery_shipment(station, customer, courier)
    admin_headers = _headers(admin.id, Role.OPERATIONS_ADMIN)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        interception = await client.post(
            f"/api/v1/returns/shipments/{shipment.id}/request-interception",
            headers={**admin_headers, "Idempotency-Key": "intercept"},
            json={"reason": "客户要求拦截"},
        )
        redelivery = await client.post(
            f"/api/v1/returns/shipments/{shipment.id}/redeliver",
            headers={**admin_headers, "Idempotency-Key": "redeliver"},
            json={"reason": "首次派送失败，重新派送"},
        )
        convert = await client.post(
            f"/api/v1/returns/shipments/{shipment.id}/convert-to-pickup",
            headers={**admin_headers, "Idempotency-Key": "convert-pickup"},
            json={"reason": "客户改为网点自取"},
        )

    assert interception.status_code == 200, interception.text
    assert interception.json()["recovery"]["status"] == "REQUESTED"
    assert redelivery.status_code == 200, redelivery.text
    assert redelivery.json()["shipment_status"] == "DELIVERY_ASSIGNED"
    assert redelivery.json()["new_task_id"] is not None
    assert convert.status_code == 200, convert.text
    assert convert.json()["shipment_status"] == "WAITING_FOR_RECIPIENT_PICKUP"

    return_shipment, _return_task = await _seed_delivery_shipment(station, customer, courier)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        approved = await client.post(
            f"/api/v1/returns/shipments/{return_shipment.id}/approve-return",
            headers={**admin_headers, "Idempotency-Key": "approve-return"},
            json={"reason": "审批退回"},
        )
        in_return = await client.post(
            f"/api/v1/returns/shipments/{return_shipment.id}/advance-return",
            headers={**admin_headers, "Idempotency-Key": "advance-return-1"},
            json={"reason": "退回发车"},
        )
        returned = await client.post(
            f"/api/v1/returns/shipments/{return_shipment.id}/advance-return",
            headers={**admin_headers, "Idempotency-Key": "advance-return-2"},
            json={"reason": "退回完成"},
        )

    assert approved.status_code == 200, approved.text
    assert approved.json()["shipment_status"] == "RETURN_APPROVED"
    assert in_return.status_code == 200, in_return.text
    assert in_return.json()["shipment_status"] == "IN_RETURN"
    assert returned.status_code == 200, returned.text
    assert returned.json()["shipment_status"] == "RETURNED"

    async with SessionFactory() as session:
        old_task = await session.get(CourierTask, task.id)
        recovery_count = await session.scalar(
            select(func.count())
            .select_from(RecoveryCase)
            .where(RecoveryCase.shipment_id.in_([shipment.id, return_shipment.id]))
        )
        recovery_sla_stages = set(
            await session.scalars(
                select(SLAInstance.stage).where(
                    SLAInstance.shipment_id.in_([shipment.id, return_shipment.id]),
                    SLAInstance.stage.in_(["DELIVERY_REDELIVERY", "PICKUP_AT_STATION", "RETURN"]),
                )
            )
        )
        return_active_sla_count = await session.scalar(
            select(func.count())
            .select_from(SLAInstance)
            .where(
                SLAInstance.shipment_id == return_shipment.id,
                SLAInstance.status.in_(["RUNNING", "PAUSED"]),
            )
        )
    assert old_task is not None
    assert old_task.status == CourierTaskStatus.CANCELLED
    assert recovery_count == 6
    assert recovery_sla_stages == {"DELIVERY_REDELIVERY", "PICKUP_AT_STATION", "RETURN"}
    assert return_active_sla_count == 0
