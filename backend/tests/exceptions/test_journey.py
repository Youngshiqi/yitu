from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from tests.exceptions.test_api import _headers
from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.exceptions.models import ExceptionCase
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment
from yitu.tracking.models import TrackingEvent

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_http_journey() -> tuple[Shipment, CourierTask, User, User, User, User, Station]:
    station = Station(
        id=uuid4(),
        code=f"JOURNEY-{uuid4().hex[:8]}",
        name="异常旅程测试网点",
        district_code="310105",
    )
    customer = User(
        id=uuid4(),
        login_name=f"journey.customer.{uuid4()}",
        display_name="异常旅程客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    courier = User(
        id=uuid4(),
        login_name=f"journey.courier.{uuid4()}",
        display_name="异常旅程快递员",
        password_hash=hash_password("密码"),
        role=Role.COURIER,
        station_id=station.id,
    )
    operator = User(
        id=uuid4(),
        login_name=f"journey.operator.{uuid4()}",
        display_name="异常旅程处理员",
        password_hash=hash_password("密码"),
        role=Role.STATION_OPERATOR,
        station_id=station.id,
    )
    admin = User(
        id=uuid4(),
        login_name=f"journey.admin.{uuid4()}",
        display_name="异常旅程运营管理员",
        password_hash=hash_password("密码"),
        role=Role.OPERATIONS_ADMIN,
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=customer.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PICKUP_ASSIGNED,
    )
    task = CourierTask(
        shipment_id=shipment.id,
        station_id=station.id,
        task_type=CourierTaskType.PICKUP,
        status=CourierTaskStatus.ACCEPTED,
        assignee_id=courier.id,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all([customer, courier, operator, admin])
        await session.flush()
        session.add(shipment)
        await session.flush()
        session.add(task)
        await session.flush()
    return shipment, task, customer, courier, operator, admin, station


async def test_http_exception_journey_blocks_resumes_and_closes_once() -> None:
    shipment, task, customer, courier, operator, admin, station = await _seed_http_journey()
    customer_headers = _headers(customer.id, Role.CUSTOMER)
    courier_headers = _headers(courier.id, Role.COURIER, station.id)
    admin_headers = _headers(admin.id, Role.OPERATIONS_ADMIN)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        opened = await client.post(
            "/api/v1/exceptions",
            headers={**customer_headers, "Idempotency-Key": "journey-open"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "客户补充前门牌号缺失",
            },
        )
        replay_open = await client.post(
            "/api/v1/exceptions",
            headers={**customer_headers, "Idempotency-Key": "journey-open"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "客户补充前门牌号缺失",
            },
        )
        blocked_before_resolve = await client.post(
            f"/api/v1/dispatch/tasks/{task.id}/confirm-pickup",
            headers=courier_headers,
        )

        case_id = opened.json()["id"]
        assign = await client.post(
            f"/api/v1/exceptions/{case_id}/assign",
            headers={**admin_headers, "Idempotency-Key": "journey-assign"},
            json={
                "assignee_id": str(operator.id),
                "responsible_station_id": str(station.id),
                "reason": "分配网点处理",
            },
        )
        start = await client.post(
            f"/api/v1/exceptions/{case_id}/start-processing",
            headers={**admin_headers, "Idempotency-Key": "journey-start"},
            json={"reason": "开始核实地址"},
        )
        wait = await client.post(
            f"/api/v1/exceptions/{case_id}/wait-for-customer",
            headers={**admin_headers, "Idempotency-Key": "journey-wait"},
            json={"reason": "等待客户补充门牌号"},
        )
        continue_processing = await client.post(
            f"/api/v1/exceptions/{case_id}/resume-processing",
            headers={**admin_headers, "Idempotency-Key": "journey-continue"},
            json={"reason": "客户已补充"},
        )
        resolved = await client.post(
            f"/api/v1/exceptions/{case_id}/resolve",
            headers={**admin_headers, "Idempotency-Key": "journey-resolve"},
            json={
                "resolution_code": "INFORMATION_CORRECTED",
                "reason": "门牌号已修正",
            },
        )
        blocked_after_resolve = await client.post(
            f"/api/v1/dispatch/tasks/{task.id}/confirm-pickup",
            headers=courier_headers,
        )
        close_too_early = await client.post(
            f"/api/v1/exceptions/{case_id}/close",
            headers={**admin_headers, "Idempotency-Key": "journey-close-too-early"},
            json={"reason": "恢复前关闭"},
        )
        resumed = await client.post(
            f"/api/v1/shipments/{shipment.id}/resume",
            headers={**admin_headers, "Idempotency-Key": "journey-resume-shipment"},
            json={
                "target_status": "PICKUP_ASSIGNED",
                "reason": "地址已修正，恢复揽收",
            },
        )
        replay_resume = await client.post(
            f"/api/v1/shipments/{shipment.id}/resume",
            headers={**admin_headers, "Idempotency-Key": "journey-resume-shipment"},
            json={
                "target_status": "PICKUP_ASSIGNED",
                "reason": "地址已修正，恢复揽收",
            },
        )
        closed = await client.post(
            f"/api/v1/exceptions/{case_id}/close",
            headers={**admin_headers, "Idempotency-Key": "journey-close"},
            json={"reason": "履约已恢复，关闭工单"},
        )
        fulfilled = await client.post(
            f"/api/v1/dispatch/tasks/{task.id}/confirm-pickup",
            headers=courier_headers,
        )

    assert opened.status_code == 201, opened.text
    assert replay_open.status_code == 201, replay_open.text
    assert replay_open.json()["id"] == opened.json()["id"]
    assert blocked_before_resolve.status_code == 409, blocked_before_resolve.text
    assert blocked_before_resolve.json()["code"] == "SHIPMENT_FULFILLMENT_BLOCKED"
    assert assign.status_code == 200, assign.text
    assert start.json()["status"] == "PROCESSING"
    assert wait.json()["status"] == "WAITING_FOR_CUSTOMER"
    assert continue_processing.json()["status"] == "PROCESSING"
    assert resolved.json()["status"] == "RESOLVED"
    assert blocked_after_resolve.status_code == 409, blocked_after_resolve.text
    assert close_too_early.status_code == 409, close_too_early.text
    assert close_too_early.json()["code"] == "RESUME_PRECONDITION_FAILED"
    assert resumed.status_code == 200, resumed.text
    assert replay_resume.status_code == 200, replay_resume.text
    assert replay_resume.json() == resumed.json()
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    assert fulfilled.status_code == 200, fulfilled.text

    async with SessionFactory() as session:
        saved_task = await session.get(CourierTask, task.id)
        saved_case = await session.get(ExceptionCase, case_id)
        active_hold_count = await session.scalar(
            select(func.count())
            .select_from(ShipmentHold)
            .where(
                ShipmentHold.shipment_id == shipment.id,
                ShipmentHold.active.is_(True),
            )
        )
        resume_tracking_count = await session.scalar(
            select(func.count())
            .select_from(TrackingEvent)
            .where(
                TrackingEvent.shipment_id == shipment.id,
                TrackingEvent.event_type == "SHIPMENT_RESUMED",
            )
        )
        resume_outbox_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE business_id = :business_id "
                    "AND payload ->> 'template_code' = 'SHIPMENT_RESUMED'"
                ),
                {"business_id": f"shipment:{shipment.id}:resumed"},
            )
        ).scalar_one()
        resume_audit_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_entries "
                    "WHERE action = 'shipment.resume' "
                    "AND resource = :resource"
                ),
                {"resource": f"shipment:{shipment.id}"},
            )
        ).scalar_one()

    assert saved_task is not None
    assert saved_task.status == CourierTaskStatus.COMPLETED
    assert saved_case is not None
    assert saved_case.blocks_fulfillment is False
    assert active_hold_count == 0
    assert resume_tracking_count == 1
    assert resume_outbox_count == 1
    assert resume_audit_count == 1
