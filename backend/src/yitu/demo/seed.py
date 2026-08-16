from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.platform.clock import Clock
from yitu.pricing.models import PricingRule
from yitu.stations.models import ServiceArea

DEMO_PASSWORD = "YituDemo2026!"
_DEMO_USERS = (
    ("30000000-0000-4000-8000-000000000001", "customer.demo", "演示客户", Role.CUSTOMER, None, "customer"),
    ("30000000-0000-4000-8000-000000000002", "courier.bijing.demo", "北京派送员", Role.COURIER, "BJS-001", "courier-bj"),
    ("30000000-0000-4000-8000-000000000003", "courier.shanghai.demo", "上海派送员", Role.COURIER, "SHS-001", "courier-sh"),
    ("30000000-0000-4000-8000-000000000004", "operator.beijing.demo", "北京网点员", Role.STATION_OPERATOR, "BJS-001", "operator-bj"),
    ("30000000-0000-4000-8000-000000000005", "operator.shanghai.demo", "上海网点员", Role.STATION_OPERATOR, "SHS-001", "operator-sh"),
    ("30000000-0000-4000-8000-000000000006", "operations.demo", "运营管理员", Role.OPERATIONS_ADMIN, None, "operations"),
)


async def seed_demo_users(session: AsyncSession) -> list[User]:
    """创建固定演示身份；已存在的身份直接复用。"""
    stations = {station.code: station.id for station in (await session.scalars(select(Station))).all()}
    users: list[User] = []
    for user_id, login_name, display_name, role, station_code, demo_key in _DEMO_USERS:
        existing = await session.scalar(select(User).where(User.demo_key == demo_key))
        if existing is not None:
            users.append(existing)
            continue
        station_id = stations.get(station_code) if station_code is not None else None
        users.append(User(id=UUID(user_id), login_name=login_name, display_name=display_name, password_hash=hash_password(DEMO_PASSWORD), role=role, station_id=station_id, demo_key=demo_key))
    session.add_all([user for user in users if user not in session])
    await session.flush()
    return users


async def seed_demo_pricing(session: AsyncSession) -> None:
    """演示环境补齐基础报价规则，不覆盖管理员维护的已有规则。"""
    defaults = (
        ("40000000-0000-4000-8000-000000000001", "SAME_CITY", 800, 200),
        ("40000000-0000-4000-8000-000000000002", "BJ_SH", 1500, 600),
        ("40000000-0000-4000-8000-000000000003", "CROSS_REGION", 1200, 500),
    )
    existing = {
        rule.route_code
        for rule in (await session.scalars(select(PricingRule))).all()
    }
    session.add_all(
        [
            PricingRule(
                id=UUID(rule_id),
                version="pricing-demo-v1",
                route_code=route,
                base_fee_cents=base_fee,
                additional_fee_cents=additional_fee,
                remote_surcharge_cents=0,
                effective_from=Clock.now(),
            )
            for rule_id, route, base_fee, additional_fee in defaults
            if route not in existing
        ]
    )
    await session.flush()


async def seed_demo_service_areas(session: AsyncSession) -> None:
    """为演示网点补齐门到门服务区域，不覆盖运营员已经维护的映射。"""
    demo_codes = {"BJS-001", "SHS-001", "GZS-001", "SZS-001"}
    stations = (
        await session.scalars(select(Station).where(Station.code.in_(demo_codes)))
    ).all()
    existing = {
        (area.district_code, area.service_type)
        for area in (await session.scalars(select(ServiceArea))).all()
    }
    session.add_all(
        [
            ServiceArea(
                district_code=station.district_code,
                service_type=service_type,
                station_id=station.id,
                version=1,
            )
            for station in stations
            for service_type in ("HOME_PICKUP", "HOME_DELIVERY")
            if (station.district_code, service_type) not in existing
        ]
    )
    await session.flush()
