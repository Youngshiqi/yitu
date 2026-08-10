from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from yitu.exceptions.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
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
