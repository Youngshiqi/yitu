from collections.abc import AsyncIterator
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.exceptions.enums import (
    ExceptionSeverity,
    ExceptionSourceType,
    ExceptionStatus,
    ExceptionType,
)
from yitu.exceptions.models import ExceptionCase, ExceptionTaskReassignment
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment
from yitu.sla.models import SLAInstance, SLAPause, SLARule

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _shipment_fixture() -> tuple[User, Station, Shipment]:
    owner = User(
        id=uuid4(),
        login_name=f"exception.customer.{uuid4()}",
        display_name="异常客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    station = Station(
        id=uuid4(),
        code=f"EX-{uuid4().hex[:8]}",
        name="异常测试网点",
        district_code="310105",
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=owner.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=PickupMethod.STATION_DROPOFF,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        session.add_all([owner, station])
        await session.flush()
        session.add(shipment)
    return owner, station, shipment


async def test_exception_case_persists_lifecycle_and_source_idempotency() -> None:
    _owner, station, shipment = await _shipment_fixture()
    source_id = uuid4()
    opened_at = datetime(2026, 8, 10, 9, 30, tzinfo=TZ)
    async with SessionFactory() as session, session.begin():
        case = ExceptionCase(
            shipment_id=shipment.id,
            case_type=ExceptionType.STATION_DELAY,
            severity=ExceptionSeverity.HIGH,
            status=ExceptionStatus.OPEN,
            source_type=ExceptionSourceType.SLA_SCAN,
            source_id=source_id,
            description="网点处理超时",
            evidence_summary={"scan_key": "scan-1"},
            blocks_fulfillment=False,
            frozen_shipment_status=None,
            reported_by=None,
            assigned_to=None,
            responsible_station_id=station.id,
            resolution_code=None,
            resolution_reason=None,
            opened_at=opened_at,
            idempotency_key="exception:sla:scan-1",
            request_id="scan-1",
        )
        session.add(case)

    async with SessionFactory() as session:
        saved = await session.scalar(
            select(ExceptionCase).where(ExceptionCase.source_id == source_id)
        )

    assert saved is not None
    assert saved.shipment_id == shipment.id
    assert saved.case_type == ExceptionType.STATION_DELAY
    assert saved.severity == ExceptionSeverity.HIGH
    assert saved.status == ExceptionStatus.OPEN
    assert saved.evidence_summary == {"scan_key": "scan-1"}
    assert saved.responsible_station_id == station.id
    assert saved.opened_at.tzinfo is not None

    with pytest.raises(IntegrityError):
        async with SessionFactory() as session, session.begin():
            session.add(
                ExceptionCase(
                    shipment_id=shipment.id,
                    case_type=ExceptionType.STATION_DELAY,
                    severity=ExceptionSeverity.HIGH,
                    status=ExceptionStatus.OPEN,
                    source_type=ExceptionSourceType.SLA_SCAN,
                    source_id=source_id,
                    description="重复扫描",
                    evidence_summary={},
                    blocks_fulfillment=False,
                    responsible_station_id=station.id,
                    opened_at=opened_at,
                    idempotency_key="exception:sla:scan-2",
                    request_id="scan-2",
                )
            )


async def test_shipment_hold_is_unique_per_source_but_allows_multiple_sources() -> None:
    owner, _station, shipment = await _shipment_fixture()
    first_source_id = uuid4()
    second_source_id = uuid4()
    async with SessionFactory() as session, session.begin():
        session.add_all(
            [
                ShipmentHold(
                    shipment_id=shipment.id,
                    source_type="EXCEPTION_CASE",
                    source_id=first_source_id,
                    frozen_status=ShipmentStatus.PENDING_PICKUP,
                    reason="地址错误",
                    active=True,
                    placed_by=owner.id,
                    placed_at=datetime(2026, 8, 10, 10, 0, tzinfo=TZ),
                    place_idempotency_key="hold:first",
                ),
                ShipmentHold(
                    shipment_id=shipment.id,
                    source_type="EXCEPTION_CASE",
                    source_id=second_source_id,
                    frozen_status=ShipmentStatus.PENDING_PICKUP,
                    reason="疑似丢失",
                    active=True,
                    placed_by=owner.id,
                    placed_at=datetime(2026, 8, 10, 10, 5, tzinfo=TZ),
                    place_idempotency_key="hold:second",
                ),
            ]
        )

    with pytest.raises(IntegrityError):
        async with SessionFactory() as session, session.begin():
            session.add(
                ShipmentHold(
                    shipment_id=shipment.id,
                    source_type="EXCEPTION_CASE",
                    source_id=first_source_id,
                    frozen_status=ShipmentStatus.PENDING_PICKUP,
                    reason="重复 Hold",
                    active=True,
                    placed_by=owner.id,
                    placed_at=datetime(2026, 8, 10, 10, 10, tzinfo=TZ),
                    place_idempotency_key="hold:duplicate",
                )
            )


async def test_cancelled_task_keeps_assignee_and_reassignment_fact() -> None:
    owner, station, shipment = await _shipment_fixture()
    reassignment_key = f"reassign:{uuid4()}"
    courier = User(
        id=uuid4(),
        login_name=f"exception.courier.{uuid4()}",
        display_name="异常快递员",
        password_hash=hash_password("密码"),
        role=Role.COURIER,
        station_id=station.id,
    )
    async with SessionFactory() as session, session.begin():
        session.add(courier)
        await session.flush()
        old_task = CourierTask(
            shipment_id=shipment.id,
            station_id=station.id,
            task_type=CourierTaskType.PICKUP,
            status=CourierTaskStatus.CANCELLED,
            assignee_id=courier.id,
            closed_reason="异常重派",
            closed_at=datetime(2026, 8, 10, 11, 0, tzinfo=TZ),
        )
        new_task = CourierTask(
            shipment_id=shipment.id,
            station_id=station.id,
            task_type=CourierTaskType.PICKUP,
            status=CourierTaskStatus.AVAILABLE,
            assignee_id=None,
        )
        session.add_all([old_task, new_task])
        await session.flush()
        old_task.replaced_by_task_id = new_task.id
        case = ExceptionCase(
            shipment_id=shipment.id,
            case_type=ExceptionType.PICKUP_FAILED,
            severity=ExceptionSeverity.MEDIUM,
            status=ExceptionStatus.PROCESSING,
            source_type=ExceptionSourceType.MANUAL,
            source_id=None,
            description="揽收失败",
            evidence_summary={},
            blocks_fulfillment=False,
            reported_by=owner.id,
            opened_at=datetime(2026, 8, 10, 10, 30, tzinfo=TZ),
            idempotency_key="exception:manual:pickup",
            request_id="request-1",
        )
        session.add(case)
        await session.flush()
        session.add(
            ExceptionTaskReassignment(
                case_id=case.id,
                old_task_id=old_task.id,
                new_task_id=new_task.id,
                reason="原快递员无法继续处理",
                actor_id=owner.id,
                idempotency_key=reassignment_key,
                created_at=datetime(2026, 8, 10, 11, 5, tzinfo=TZ),
            )
        )

    async with SessionFactory() as session:
        saved = await session.get(CourierTask, old_task.id)
        reassignment = await session.scalar(
            select(ExceptionTaskReassignment).where(
                ExceptionTaskReassignment.idempotency_key == reassignment_key
            )
        )

    assert saved is not None
    assert saved.status == CourierTaskStatus.CANCELLED
    assert saved.assignee_id == courier.id
    assert saved.replaced_by_task_id == new_task.id
    assert reassignment is not None
    assert reassignment.old_task_id == old_task.id
    assert reassignment.new_task_id == new_task.id


async def test_sla_pause_tracks_source_actor_and_idempotency_key() -> None:
    owner, _station, shipment = await _shipment_fixture()
    async with SessionFactory() as session, session.begin():
        rule = SLARule(
            version=f"sla-exception-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="PICKUP",
            target_work_hours=4,
            target_natural_hours=None,
            effective_from=datetime(2026, 8, 10, 8, 0, tzinfo=TZ),
            active=True,
        )
        session.add(rule)
        await session.flush()
        instance = SLAInstance(
            shipment_id=shipment.id,
            owner_id=owner.id,
            rule_id=rule.id,
            rule_version=rule.version,
            stage=rule.stage,
            status="PAUSED",
            started_at=datetime(2026, 8, 10, 9, 0, tzinfo=TZ),
            promised_delivery_at=datetime(2026, 8, 10, 13, 0, tzinfo=TZ),
        )
        session.add(instance)
        await session.flush()
        source_id = uuid4()
        pause = SLAPause(
            instance_id=instance.id,
            reason="等待客户补充地址",
            reason_code="WAITING_FOR_ADDRESS",
            source_type="EXCEPTION_CASE",
            source_id=source_id,
            actor_id=owner.id,
            pause_idempotency_key="sla-pause:1",
            started_at=datetime(2026, 8, 10, 10, 0, tzinfo=TZ),
        )
        session.add(pause)

    async with SessionFactory() as session:
        saved = await session.scalar(
            select(SLAPause).where(SLAPause.source_id == source_id)
        )

    assert saved is not None
    assert saved.reason_code == "WAITING_FOR_ADDRESS"
    assert saved.source_type == "EXCEPTION_CASE"
    assert saved.actor_id == owner.id
    assert saved.pause_idempotency_key == "sla-pause:1"
    assert saved.started_at.tzinfo is not None
