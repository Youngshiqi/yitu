from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password
from yitu.platform.clock import Clock
from yitu.pricing.models import PricingRule
from yitu.sla.models import SLAInstance, SLARule
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
    """演示环境重置为基础报价规则：历史规则标记失效，写入三条贴合现实的线路。"""
    now = Clock.now()
    # 运费规则被历史报价/支付/运单外键引用（RESTRICT），标记失效而非物理删除。
    await session.execute(
        update(PricingRule)
        .where(PricingRule.version != "pricing-demo-v1")
        .values(effective_to=now)
    )
    # 首重 1kg，续重每 500g 一档，金额为整数分，贴合现实快递区间。
    targets = (
        ("40000000-0000-4000-8000-000000000001", "SAME_CITY", 800, 150),
        ("40000000-0000-4000-8000-000000000002", "BJ_SH", 1500, 500),
        ("40000000-0000-4000-8000-000000000003", "CROSS_REGION", 1800, 700),
    )
    for rule_id, route, base_fee, additional_fee in targets:
        rule = await session.get(PricingRule, UUID(rule_id))
        if rule is None:
            session.add(
                PricingRule(
                    id=UUID(rule_id),
                    version="pricing-demo-v1",
                    route_code=route,
                    base_fee_cents=base_fee,
                    additional_fee_cents=additional_fee,
                    remote_surcharge_cents=0,
                    effective_from=now,
                )
            )
        else:
            rule.base_fee_cents = base_fee
            rule.additional_fee_cents = additional_fee
            rule.remote_surcharge_cents = 0
            rule.effective_from = now
            rule.effective_to = None
    await session.flush()


async def seed_demo_service_areas(session: AsyncSession) -> None:
    """为演示网点补齐门到门服务区域，不覆盖运营员已经维护的映射。"""
    demo_codes = {"BJS-001", "SHS-001"}
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


async def seed_demo_sla_rules(session: AsyncSession) -> None:
    """Provide conservative default stage targets for the demo environment."""
    # 只保留演示版本规则，清理运营测试残留的其他版本。
    stray_rule_ids = (
        await session.scalars(select(SLARule.id).where(SLARule.version != "sla-demo-v1"))
    ).all()
    if stray_rule_ids:
        await session.execute(delete(SLAInstance).where(SLAInstance.rule_id.in_(stray_rule_ids)))
        await session.execute(delete(SLARule).where(SLARule.id.in_(stray_rule_ids)))

    stages = (("PICKUP", 9), ("LINEHAUL", 18), ("DELIVERY", 18))
    existing = {
        rule.stage
        for rule in (
            await session.scalars(
                select(SLARule).where(
                    SLARule.route_code == "DEFAULT",
                    SLARule.service_type == "STANDARD",
                )
            )
        ).all()
    }
    session.add_all(
        [
            SLARule(
                id=UUID(f"50000000-0000-4000-8000-00000000000{index}"),
                version="sla-demo-v1",
                route_code="DEFAULT",
                service_type="STANDARD",
                stage=stage,
                target_work_hours=hours,
                effective_from=Clock.now(),
                active=True,
            )
            for index, (stage, hours) in enumerate(stages, start=1)
            if stage not in existing
        ]
    )
    await session.flush()
