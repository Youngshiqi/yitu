from sqlalchemy import inspect

from yitu.identity.models import Role, Station, User


def test_role_contains_five_business_roles() -> None:
    assert {role.value for role in Role} == {
        "CUSTOMER",
        "COURIER",
        "STATION_OPERATOR",
        "OPERATIONS_ADMIN",
        "SYSTEM_ADMIN",
    }


def test_user_has_unique_login_and_station_scope() -> None:
    user_columns = {column.name for column in inspect(User).columns}

    assert {"id", "login_name", "password_hash", "role", "station_id"}.issubset(
        user_columns
    )
    assert any(
        constraint.columns.keys() == ["login_name"]
        for constraint in User.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_demo_identity_requires_stable_uuid_and_role() -> None:
    station = Station(code="SHA-001", name="上海虹桥网点", district_code="310105")
    user = User(
        login_name="customer.demo",
        display_name="演示客户",
        password_hash="$argon2id$v=19$demo",
        role=Role.CUSTOMER,
        station=station,
        demo_key="customer-shanghai",
    )

    assert User.__table__.primary_key.columns["id"].default is not None
    assert user.role is Role.CUSTOMER
    assert user.station is station
    assert user.demo_key == "customer-shanghai"
