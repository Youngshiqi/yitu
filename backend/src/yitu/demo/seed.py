from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role, Station, User
from yitu.identity.security import hash_password

DEMO_PASSWORD = "YituDemo2026!"
_DEMO_USERS = (
    ("30000000-0000-4000-8000-000000000001", "customer.demo", "演示客户", Role.CUSTOMER, None, "customer"),
    ("30000000-0000-4000-8000-000000000002", "courier.bijing.demo", "北京派送员", Role.COURIER, "BJS-001", "courier-bj"),
    ("30000000-0000-4000-8000-000000000003", "courier.shanghai.demo", "上海派送员", Role.COURIER, "SHS-001", "courier-sh"),
    ("30000000-0000-4000-8000-000000000004", "operator.beijing.demo", "北京网点员", Role.STATION_OPERATOR, "BJS-001", "operator-bj"),
    ("30000000-0000-4000-8000-000000000005", "operator.shanghai.demo", "上海网点员", Role.STATION_OPERATOR, "SHS-001", "operator-sh"),
    ("30000000-0000-4000-8000-000000000006", "operations.demo", "运营管理员", Role.OPERATIONS_ADMIN, None, "operations"),
    ("30000000-0000-4000-8000-000000000007", "system.demo", "系统管理员", Role.SYSTEM_ADMIN, None, "system"),
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
