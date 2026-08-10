from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.exceptions.test_cases import _seed_customer_shipment, _seed_operator
from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role, User
from yitu.identity.security import create_access_token, hash_password
from yitu.main import create_app
from yitu.platform.database import SessionFactory, dispose_database

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


def _headers(user_id: object, role: Role, station_id: object | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user_id, role.value, station_id)}",
    }


async def test_post_exception_requires_idempotency_key() -> None:
    owner, shipment = await _seed_customer_shipment()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/exceptions",
            headers=_headers(owner.id, Role.CUSTOMER),
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "收件地址缺少门牌号",
            },
        )

    assert response.status_code == 422


async def test_customer_can_open_get_and_list_only_own_cases() -> None:
    owner, shipment = await _seed_customer_shipment()
    other_owner, other_shipment = await _seed_customer_shipment()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        opened = await client.post(
            "/api/v1/exceptions",
            headers={**_headers(owner.id, Role.CUSTOMER), "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "收件地址缺少门牌号",
            },
        )
        assert opened.status_code == 201, opened.text
        other = await client.post(
            "/api/v1/exceptions",
            headers={**_headers(other_owner.id, Role.CUSTOMER), "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(other_shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "另一个客户的异常",
            },
        )
        assert other.status_code == 201, other.text

        listed = await client.get(
            "/api/v1/exceptions",
            headers=_headers(owner.id, Role.CUSTOMER),
        )
        detail = await client.get(
            f"/api/v1/exceptions/{opened.json()['id']}",
            headers=_headers(owner.id, Role.CUSTOMER),
        )
        forbidden_detail = await client.get(
            f"/api/v1/exceptions/{other.json()['id']}",
            headers=_headers(owner.id, Role.CUSTOMER),
        )

    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == opened.json()["id"]
    assert detail.status_code == 200
    assert detail.json()["shipment_id"] == str(shipment.id)
    assert forbidden_detail.status_code == 404


async def test_operations_admin_can_drive_case_lifecycle_via_api() -> None:
    owner, shipment = await _seed_customer_shipment()
    operator, station = await _seed_operator()
    admin_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        opened = await client.post(
            "/api/v1/exceptions",
            headers={**_headers(owner.id, Role.CUSTOMER), "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "ADDRESS_ERROR",
                "description": "收件地址缺少门牌号",
            },
        )
        assert opened.status_code == 201, opened.text
        case_id = opened.json()["id"]
        admin_headers = _headers(admin_id, Role.OPERATIONS_ADMIN)

        assign = await client.post(
            f"/api/v1/exceptions/{case_id}/assign",
            headers={**admin_headers, "Idempotency-Key": f"assign-{uuid4()}"},
            json={
                "assignee_id": str(operator.id),
                "responsible_station_id": str(station.id),
                "reason": "分配给网点处理",
            },
        )
        start = await client.post(
            f"/api/v1/exceptions/{case_id}/start-processing",
            headers={**admin_headers, "Idempotency-Key": f"start-{uuid4()}"},
            json={"reason": "开始处理"},
        )
        wait = await client.post(
            f"/api/v1/exceptions/{case_id}/wait-for-customer",
            headers={**admin_headers, "Idempotency-Key": f"wait-{uuid4()}"},
            json={"reason": "等待客户补充"},
        )
        resume = await client.post(
            f"/api/v1/exceptions/{case_id}/resume-processing",
            headers={**admin_headers, "Idempotency-Key": f"resume-{uuid4()}"},
            json={"reason": "客户已补充"},
        )
        resolve = await client.post(
            f"/api/v1/exceptions/{case_id}/resolve",
            headers={**admin_headers, "Idempotency-Key": f"resolve-{uuid4()}"},
            json={
                "resolution_code": "INFORMATION_CORRECTED",
                "reason": "地址已修正",
            },
        )
        close = await client.post(
            f"/api/v1/exceptions/{case_id}/close",
            headers={**admin_headers, "Idempotency-Key": f"close-{uuid4()}"},
            json={"reason": "处理完成"},
        )

    assert assign.status_code == 200, assign.text
    assert assign.json()["status"] == "ASSIGNED"
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "PROCESSING"
    assert wait.status_code == 200, wait.text
    assert wait.json()["status"] == "WAITING_FOR_CUSTOMER"
    assert resume.status_code == 200, resume.text
    assert resume.json()["status"] == "PROCESSING"
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["status"] == "RESOLVED"
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "CLOSED"


async def test_operations_admin_can_reassign_task_via_api() -> None:
    _owner, shipment = await _seed_customer_shipment()
    operator, station = await _seed_operator()
    admin_id = uuid4()
    async with SessionFactory() as session, session.begin():
        session.add(
            User(
                id=admin_id,
                login_name=f"api.admin.{uuid4()}",
                display_name="运营管理员",
                password_hash=hash_password("密码"),
                role=Role.OPERATIONS_ADMIN,
            )
        )
        await session.flush()
        old_task = CourierTask(
            shipment_id=shipment.id,
            station_id=station.id,
            task_type=CourierTaskType.PICKUP,
            status=CourierTaskStatus.ACCEPTED,
            assignee_id=operator.id,
        )
        session.add(old_task)
        await session.flush()
        old_task_id = old_task.id

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        admin_headers = _headers(admin_id, Role.OPERATIONS_ADMIN)
        opened = await client.post(
            "/api/v1/exceptions",
            headers={**admin_headers, "Idempotency-Key": f"case-{uuid4()}"},
            json={
                "shipment_id": str(shipment.id),
                "case_type": "PICKUP_FAILED",
                "description": "揽收失败",
            },
        )
        assert opened.status_code == 201, opened.text
        case_id = opened.json()["id"]
        assign = await client.post(
            f"/api/v1/exceptions/{case_id}/assign",
            headers={**admin_headers, "Idempotency-Key": f"assign-{uuid4()}"},
            json={
                "assignee_id": str(operator.id),
                "responsible_station_id": str(station.id),
                "reason": "分配处理",
            },
        )
        assert assign.status_code == 200, assign.text
        reassigned = await client.post(
            f"/api/v1/exceptions/{case_id}/reassign-task",
            headers={**admin_headers, "Idempotency-Key": f"reassign-{uuid4()}"},
            json={
                "old_task_id": str(old_task_id),
                "reason": "原任务无法继续处理",
            },
        )

    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["old_task_id"] == str(old_task_id)
    assert reassigned.json()["new_task_id"] != str(old_task_id)
