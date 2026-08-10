from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from yitu.identity.models import Role
from yitu.identity.service import (
    CurrentUser,
    get_current_user,
    require_resource_owner,
    require_roles,
    require_station_scope,
)


def credentials_for(
    user_id: UUID, role: Role, station_id: UUID | None
) -> HTTPAuthorizationCredentials:
    from yitu.identity.security import create_access_token

    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token(user_id, role.value, station_id),
    )


async def test_current_user_is_built_from_jwt_claims() -> None:
    user_id = uuid4()
    station_id = uuid4()

    current_user = await get_current_user(
        credentials_for(user_id, Role.COURIER, station_id)
    )

    assert current_user == CurrentUser(
        id=user_id, role=Role.COURIER, station_id=station_id
    )


async def test_role_and_station_scope_reject_wrong_access() -> None:
    station_id = uuid4()
    current_user = CurrentUser(id=uuid4(), role=Role.COURIER, station_id=station_id)

    require_roles(Role.COURIER)(current_user)
    with pytest.raises(Exception, match="角色权限不足"):
        require_roles(Role.CUSTOMER)(current_user)
    with pytest.raises(Exception, match="网点范围不足"):
        require_station_scope(uuid4(), current_user)


def test_customer_can_only_access_owned_resource() -> None:
    current_user = CurrentUser(id=uuid4(), role=Role.CUSTOMER, station_id=None)

    require_resource_owner(current_user.id, current_user)
    with pytest.raises(Exception, match="只能访问本人资源"):
        require_resource_owner(uuid4(), current_user)
