from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from yitu.exceptions.enums import ExceptionType, ResolutionCode
from yitu.exceptions.models import ExceptionCase
from yitu.exceptions.schemas import ExceptionAssign, ExceptionCreate, ExceptionResolve
from yitu.exceptions.service import ExceptionService
from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment
from yitu.shipments.schemas import ShipmentResumeCommand
from yitu.sla.models import SLAInstance, SLAPause, SLARule
from yitu.sla.service import SLAService

pytestmark = pytest.mark.asyncio(loop_scope="function")
TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


async def _seed_recovery_context() -> tuple[Shipment, CurrentUser, User, Station]:
    station = Station(
        id=uuid4(),
        code=f"REC-{uuid4().hex[:8]}",
        name="履约恢复测试网点",
        district_code="310105",
    )
    customer = User(
        id=uuid4(),
        login_name=f"recovery.customer.{uuid4()}",
        display_name="恢复测试客户",
        password_hash=hash_password("密码"),
        role=Role.CUSTOMER,
    )
    admin_user = User(
        id=uuid4(),
        login_name=f"recovery.admin.{uuid4()}",
        display_name="恢复运营管理员",
        password_hash=hash_password("密码"),
        role=Role.OPERATIONS_ADMIN,
    )
    operator = User(
        id=uuid4(),
        login_name=f"recovery.operator.{uuid4()}",
        display_name="恢复处理员",
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
        pickup_method=PickupMethod.DOOR_PICKUP,
        delivery_method=DeliveryMethod.HOME_DELIVERY,
        status=ShipmentStatus.PENDING_PICKUP,
    )
    async with SessionFactory() as session, session.begin():
        session.add(station)
        await session.flush()
        session.add_all([customer, admin_user, operator])
        await session.flush()
        session.add(shipment)
    return (
        shipment,
        CurrentUser(id=admin_user.id, role=Role.OPERATIONS_ADMIN, station_id=None),
        operator,
        station,
    )


async def _open_assigned_processing_case(
    shipment: Shipment,
    admin: CurrentUser,
    operator: User,
    station: Station,
) -> ExceptionCase:
    async with SessionFactory() as session, session.begin():
        service = ExceptionService(session)
        case_view = await service.open_case(
            ExceptionCreate(
                shipment_id=shipment.id,
                case_type=ExceptionType.ADDRESS_ERROR,
                description="收件地址缺少门牌号",
            ),
            admin,
            f"recovery:open:{uuid4()}",
            "request-open",
        )
        await service.assign_case(
            case_view.id,
            ExceptionAssign(
                assignee_id=operator.id,
                responsible_station_id=station.id,
                reason="分配处理",
            ),
            admin,
            f"recovery:assign:{uuid4()}",
            "request-assign",
        )
        await service.apply_action(
            case_view.id,
            "start_processing",
            admin,
            f"recovery:start:{uuid4()}",
            "request-start",
            reason="开始处理",
        )
        case = await session.get(ExceptionCase, case_view.id)
        assert case is not None
        return case


async def _attach_source_pause(shipment: Shipment, case_id: object, actor_id: object) -> SLAInstance:
    start_at = datetime(2026, 8, 10, 8, 0, tzinfo=TZ)
    async with SessionFactory() as session, session.begin():
        rule = SLARule(
            version=f"recovery-sla-{uuid4()}",
            route_code="TEST",
            service_type="STANDARD",
            stage="PICKUP",
            target_natural_hours=240,
            effective_from=start_at - timedelta(days=1),
        )
        session.add(rule)
        await session.flush()
        instance = await SLAService(session).start(shipment.id, "TEST", "PICKUP")
        await SLAService(session).pause_for_source(
            instance.id,
            reason="等待客户补充地址",
            reason_code="WAITING_FOR_ADDRESS",
            source_type="EXCEPTION_CASE",
            source_id=case_id,  # type: ignore[arg-type]
            actor_id=actor_id,  # type: ignore[arg-type]
            idempotency_key=f"recovery:sla:pause:{case_id}",
        )
        return instance


async def test_resume_releases_holds_resumes_sla_and_writes_facts() -> None:
    shipment, admin, operator, station = await _seed_recovery_context()
    case = await _open_assigned_processing_case(shipment, admin, operator, station)
    instance = await _attach_source_pause(shipment, case.id, admin.id)
    async with SessionFactory() as session, session.begin():
        service = ExceptionService(session)
        await service.resolve_case(
            case.id,
            ExceptionResolve(
                resolution_code=ResolutionCode.INFORMATION_CORRECTED,
                reason="地址已修正",
            ),
            admin,
            "recovery:resolve",
            "request-resolve",
        )
        result = await service.resume_shipment(
            shipment.id,
            ShipmentResumeCommand(
                target_status=ShipmentStatus.PENDING_PICKUP,
                reason="确认可继续揽收",
            ),
            admin,
            "recovery:resume",
            "request-resume",
        )

    async with SessionFactory() as session:
        hold = await session.scalar(select(ShipmentHold).where(ShipmentHold.source_id == case.id))
        saved_case = await session.get(ExceptionCase, case.id)
        pause = await session.scalar(select(SLAPause).where(SLAPause.instance_id == instance.id))
        outbox = (
            await session.execute(
                text(
                    "SELECT payload FROM outbox_events "
                    "WHERE business_id = :business_id"
                ),
                {"business_id": f"shipment:{shipment.id}:resumed"},
            )
        ).scalar_one_or_none()

    assert result.status == ShipmentStatus.PENDING_PICKUP
    assert result.resumed_hold_count == 1
    assert hold is not None
    assert hold.active is False
    assert saved_case is not None
    assert saved_case.blocks_fulfillment is False
    assert pause is not None
    assert pause.ended_at is not None
    assert pause.resume_idempotency_key == f"sla:resume:{case.id}:recovery:resume"
    assert outbox is not None
    assert outbox["template_code"] == "SHIPMENT_RESUMED"


async def test_resume_rejects_when_blocking_case_is_unresolved() -> None:
    shipment, admin, operator, station = await _seed_recovery_context()
    await _open_assigned_processing_case(shipment, admin, operator, station)

    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as error:
            await ExceptionService(session).resume_shipment(
                shipment.id,
                ShipmentResumeCommand(
                    target_status=ShipmentStatus.PENDING_PICKUP,
                    reason="尝试提前恢复",
                ),
                admin,
                "recovery:resume:unresolved",
                "request-resume",
            )

    assert error.value.code == "UNRESOLVED_BLOCKING_CASES"


async def test_resume_rejects_target_status_mismatch_and_missing_hold() -> None:
    shipment, admin, operator, station = await _seed_recovery_context()
    case = await _open_assigned_processing_case(shipment, admin, operator, station)
    async with SessionFactory() as session, session.begin():
        await ExceptionService(session).resolve_case(
            case.id,
            ExceptionResolve(
                resolution_code=ResolutionCode.INFORMATION_CORRECTED,
                reason="地址已修正",
            ),
            admin,
            "recovery:resolve:mismatch",
            "request-resolve",
        )
        with pytest.raises(AppError) as mismatch:
            await ExceptionService(session).resume_shipment(
                shipment.id,
                ShipmentResumeCommand(
                    target_status=ShipmentStatus.AT_ORIGIN_STATION,
                    reason="错误目标阶段",
                ),
                admin,
                "recovery:resume:mismatch",
                "request-resume",
            )

    other_shipment, other_admin, _operator, _station = await _seed_recovery_context()
    async with SessionFactory() as session, session.begin():
        with pytest.raises(AppError) as missing_hold:
            await ExceptionService(session).resume_shipment(
                other_shipment.id,
                ShipmentResumeCommand(
                    target_status=ShipmentStatus.PENDING_PICKUP,
                    reason="无冻结恢复",
                ),
                other_admin,
                "recovery:resume:no-hold",
                "request-resume",
            )

    assert mismatch.value.code == "RESUME_TARGET_MISMATCH"
    assert missing_hold.value.code == "SHIPMENT_NOT_BLOCKED"


async def test_blocking_case_cannot_close_before_resume() -> None:
    shipment, admin, operator, station = await _seed_recovery_context()
    case = await _open_assigned_processing_case(shipment, admin, operator, station)

    async with SessionFactory() as session, session.begin():
        service = ExceptionService(session)
        await service.resolve_case(
            case.id,
            ExceptionResolve(
                resolution_code=ResolutionCode.INFORMATION_CORRECTED,
                reason="地址已修正",
            ),
            admin,
            "recovery:resolve:close",
            "request-resolve",
        )
        with pytest.raises(AppError) as error:
            await service.apply_action(
                case.id,
                "close",
                admin,
                "recovery:close:blocked",
                "request-close",
                reason="尝试关闭",
            )

    assert error.value.code == "RESUME_PRECONDITION_FAILED"
