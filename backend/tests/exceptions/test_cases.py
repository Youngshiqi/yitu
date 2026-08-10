from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.exceptions.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ResolutionCode,
)
from yitu.exceptions.models import ExceptionTaskReassignment
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_customer_shipment(owner_id: UUID | None = None) -> tuple[User, Shipment]:
    station = Station(
        id=uuid4(),
        code=f"CASE-{uuid4().hex[:8]}",
        name="异常开单测试网点",
        district_code="310105",
    )
    owner = User(
        id=owner_id or uuid4(),
        login_name=f"case.customer.{uuid4()}",
        display_name="异常客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    shipment = Shipment(
        id=uuid4(),
        shipment_no=f"YT{uuid4().hex[:16].upper()}",
        owner_id=owner.id,
        origin_station_id=station.id,
        destination_station_id=station.id,
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add(owner)
        await session.flush()
        session.add(shipment)
    return owner, shipment


async def _seed_operator() -> tuple[User, Station]:
    station = Station(
        id=uuid4(),
        code=f"CASE-OP-{uuid4().hex[:8]}",
        name="异常处理测试网点",
        district_code="310105",
    )
    operator = User(
        id=uuid4(),
        login_name=f"case.operator.{uuid4()}",
        display_name="异常处理员",
        password_hash=hash_password("密码"),
        role=Role.STATION_OPERATOR,
        station_id=station.id,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add(operator)
    return operator, station


async def test_customer_open_case_applies_policy_hold_outbox_and_idempotency() -> None:
    from yitu.exceptions.schemas import ExceptionCreate
    from yitu.exceptions.service import ExceptionService

    owner, shipment = await _seed_customer_shipment()
    actor = CurrentUser(id=owner.id, role=Role.CUSTOMER, station_id=None)
    request = ExceptionCreate(
        shipment_id=shipment.id,
        case_type=ExceptionType.ADDRESS_ERROR,
        description="收件地址缺少门牌号",
        evidence_summary={"source": "customer"},
    )
    async with SessionFactory() as session, session.begin():
        first = await ExceptionService(session).open_case(
            request,
            actor,
            "exception-open-1",
            "request-1",
        )
        replay = await ExceptionService(session).open_case(
            request,
            actor,
            "exception-open-1",
            "request-2",
        )

    assert replay.id == first.id
    assert first.status == ExceptionStatus.OPEN
    assert first.severity == ExceptionSeverity.MEDIUM
    assert first.blocks_fulfillment is True

    async with SessionFactory() as session:
        hold_count = await session.scalar(
            select(func.count()).select_from(ShipmentHold).where(
                ShipmentHold.shipment_id == shipment.id,
                ShipmentHold.active.is_(True),
            )
        )
        outbox = (
            await session.execute(
                text(
                    "SELECT payload FROM outbox_events "
                    "WHERE event_type = 'notification.requested' "
                    "AND business_id = :business_id"
                ),
                {"business_id": f"exception:{first.id}"},
            )
        ).scalar_one_or_none()

    assert hold_count == 1
    assert outbox is not None
    assert outbox["template_code"] == "EXCEPTION_OPENED"


async def test_customer_cannot_open_unreportable_type_or_other_customer_shipment() -> None:
    from yitu.exceptions.schemas import ExceptionCreate
    from yitu.exceptions.service import ExceptionService

    owner, shipment = await _seed_customer_shipment()
    other_owner, other_shipment = await _seed_customer_shipment()
    actor = CurrentUser(id=owner.id, role=Role.CUSTOMER, station_id=None)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as type_error:
            await ExceptionService(session).open_case(
                ExceptionCreate(
                    shipment_id=shipment.id,
                    case_type=ExceptionType.PICKUP_FAILED,
                    description="客户不能上报揽收失败",
                ),
                actor,
                "exception-open-type",
                "request-type",
            )
        with pytest.raises(AppError) as scope_error:
            await ExceptionService(session).open_case(
                ExceptionCreate(
                    shipment_id=other_shipment.id,
                    case_type=ExceptionType.ADDRESS_ERROR,
                    description="不能替别人开异常",
                ),
                actor,
                "exception-open-scope",
                "request-scope",
            )

    assert other_owner.id != owner.id
    assert type_error.value.code == "EXCEPTION_TYPE_NOT_ALLOWED"
    assert scope_error.value.code == "FORBIDDEN_EXCEPTION_SCOPE"


async def test_list_cases_is_scoped_to_customer_shipments() -> None:
    from yitu.exceptions.schemas import ExceptionCreate
    from yitu.exceptions.service import ExceptionService

    owner, shipment = await _seed_customer_shipment()
    other_owner, other_shipment = await _seed_customer_shipment()
    owner_actor = CurrentUser(id=owner.id, role=Role.CUSTOMER, station_id=None)
    other_actor = CurrentUser(id=other_owner.id, role=Role.CUSTOMER, station_id=None)
    async with SessionFactory() as session, session.begin():
        await ExceptionService(session).open_case(
            ExceptionCreate(
                shipment_id=shipment.id,
                case_type=ExceptionType.ADDRESS_ERROR,
                description="本人异常",
            ),
            owner_actor,
            "case:list:owner",
            "request-owner",
        )
        await ExceptionService(session).open_case(
            ExceptionCreate(
                shipment_id=other_shipment.id,
                case_type=ExceptionType.ADDRESS_ERROR,
                description="他人异常",
            ),
            other_actor,
            "case:list:other",
            "request-other",
        )

    async with SessionFactory() as session:
        cases, total = await ExceptionService(session).list_cases(owner_actor)

    assert total == 1
    assert [case.shipment_id for case in cases] == [shipment.id]


async def test_operations_admin_can_drive_case_lifecycle() -> None:
    from yitu.exceptions.schemas import (
        ExceptionAssign,
        ExceptionCreate,
        ExceptionResolve,
    )
    from yitu.exceptions.service import ExceptionService
    from yitu.shipments.schemas import ShipmentResumeCommand

    owner, shipment = await _seed_customer_shipment()
    operator, station = await _seed_operator()
    admin = CurrentUser(id=uuid4(), role=Role.OPERATIONS_ADMIN, station_id=None)
    customer = CurrentUser(id=owner.id, role=Role.CUSTOMER, station_id=None)
    async with SessionFactory() as session, session.begin():
        session.add(
            User(
                id=admin.id,
                login_name=f"case.admin.lifecycle.{uuid4()}",
                display_name="生命周期运营管理员",
                password_hash=hash_password("密码"),
                role=Role.OPERATIONS_ADMIN,
            )
        )
        await session.flush()
        case = await ExceptionService(session).open_case(
            ExceptionCreate(
                shipment_id=shipment.id,
                case_type=ExceptionType.ADDRESS_ERROR,
                description="地址缺少门牌号",
            ),
            customer,
            "case:lifecycle:open",
            "request-open",
        )
        assigned = await ExceptionService(session).assign_case(
            case.id,
            ExceptionAssign(
                assignee_id=operator.id,
                responsible_station_id=station.id,
                reason="分配给目的网点处理",
            ),
            admin,
            "case:lifecycle:assign",
            "request-assign",
        )
        processing = await ExceptionService(session).apply_action(
            case.id,
            "start_processing",
            admin,
            "case:lifecycle:start",
            "request-start",
            reason="开始核实",
        )
        waiting = await ExceptionService(session).apply_action(
            case.id,
            "wait_for_customer",
            admin,
            "case:lifecycle:wait",
            "request-wait",
            reason="等待客户补充门牌号",
        )
        resumed = await ExceptionService(session).apply_action(
            case.id,
            "resume_processing",
            admin,
            "case:lifecycle:resume",
            "request-resume",
            reason="客户已补充",
        )
        resolved = await ExceptionService(session).resolve_case(
            case.id,
            ExceptionResolve(
                resolution_code=ResolutionCode.INFORMATION_CORRECTED,
                reason="地址已修正",
            ),
            admin,
            "case:lifecycle:resolve",
            "request-resolve",
        )
        resumed_shipment = await ExceptionService(session).resume_shipment(
            shipment.id,
            ShipmentResumeCommand(
                target_status=ShipmentStatus.PENDING_PICKUP,
                reason="确认地址已修正，可恢复履约",
            ),
            admin,
            "case:lifecycle:resume-shipment",
            "request-resume-shipment",
        )
        closed = await ExceptionService(session).apply_action(
            case.id,
            "close",
            admin,
            "case:lifecycle:close",
            "request-close",
            reason="处理完成",
        )

    assert assigned.status == ExceptionStatus.ASSIGNED
    assert assigned.assigned_to == operator.id
    assert assigned.responsible_station_id == station.id
    assert processing.status == ExceptionStatus.PROCESSING
    assert waiting.status == ExceptionStatus.WAITING_FOR_CUSTOMER
    assert resumed.status == ExceptionStatus.PROCESSING
    assert resolved.status == ExceptionStatus.RESOLVED
    assert resumed_shipment.status == ShipmentStatus.PENDING_PICKUP
    assert closed.status == ExceptionStatus.CLOSED


async def test_customer_cannot_drive_case_lifecycle() -> None:
    from yitu.exceptions.schemas import ExceptionCreate
    from yitu.exceptions.service import ExceptionService

    owner, shipment = await _seed_customer_shipment()
    customer = CurrentUser(id=owner.id, role=Role.CUSTOMER, station_id=None)
    async with SessionFactory() as session, session.begin():
        case = await ExceptionService(session).open_case(
            ExceptionCreate(
                shipment_id=shipment.id,
                case_type=ExceptionType.ADDRESS_ERROR,
                description="地址缺少门牌号",
            ),
            customer,
            "case:forbidden:open",
            "request-open",
        )
        with pytest.raises(AppError) as error:
            await ExceptionService(session).apply_action(
                case.id,
                "start_processing",
                customer,
                "case:forbidden:start",
                "request-start",
            )

    assert error.value.code == "FORBIDDEN_EXCEPTION_ACTION"


async def test_operations_admin_can_reassign_open_task() -> None:
    from yitu.exceptions.schemas import (
        ExceptionAssign,
        ExceptionCreate,
        ExceptionTaskReassign,
    )
    from yitu.exceptions.service import ExceptionService

    _owner, shipment = await _seed_customer_shipment()
    operator, station = await _seed_operator()
    courier = User(
        id=uuid4(),
        login_name=f"case.courier.{uuid4()}",
        display_name="原快递员",
        password_hash=hash_password("密码"),
        role=Role.COURIER,
        station_id=station.id,
    )
    admin_user = User(
        id=uuid4(),
        login_name=f"case.admin.{uuid4()}",
        display_name="运营管理员",
        password_hash=hash_password("密码"),
        role=Role.OPERATIONS_ADMIN,
    )
    admin = CurrentUser(id=admin_user.id, role=Role.OPERATIONS_ADMIN, station_id=None)
    async with SessionFactory() as session, session.begin():
        session.add_all([courier, admin_user])
        await session.flush()
        old_task = CourierTask(
            shipment_id=shipment.id,
            station_id=station.id,
            task_type=CourierTaskType.PICKUP,
            status=CourierTaskStatus.ACCEPTED,
            assignee_id=courier.id,
        )
        session.add(old_task)
        await session.flush()
        case = await ExceptionService(session).open_case(
            ExceptionCreate(
                shipment_id=shipment.id,
                case_type=ExceptionType.PICKUP_FAILED,
                description="揽收失败",
            ),
            admin,
            "case:reassign:open",
            "request-open",
        )
        await ExceptionService(session).assign_case(
            case.id,
            ExceptionAssign(
                assignee_id=operator.id,
                responsible_station_id=station.id,
                reason="分配处理",
            ),
            admin,
            "case:reassign:assign",
            "request-assign",
        )
        reassignment = await ExceptionService(session).reassign_task(
            case.id,
            ExceptionTaskReassign(old_task_id=old_task.id, reason="原快递员无法继续处理"),
            admin,
            "case:reassign:task",
            "request-reassign",
        )

    async with SessionFactory() as session:
        saved_old = await session.get(CourierTask, old_task.id)
        saved_new = await session.get(CourierTask, reassignment.new_task_id)
        fact = await session.get(ExceptionTaskReassignment, reassignment.id)

    assert saved_old is not None
    assert saved_old.status == CourierTaskStatus.CANCELLED
    assert saved_old.assignee_id == courier.id
    assert saved_old.closed_reason == "原快递员无法继续处理"
    assert saved_old.replaced_by_task_id == reassignment.new_task_id
    assert saved_new is not None
    assert saved_new.status == CourierTaskStatus.AVAILABLE
    assert saved_new.assignee_id is None
    assert fact is not None
    assert fact.old_task_id == old_task.id
    assert fact.new_task_id == saved_new.id
