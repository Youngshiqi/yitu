from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from yitu.identity.models import Role
from yitu.identity.security import decode_access_token
from yitu.platform.errors import AppError

_bearer = HTTPBearer(auto_error=False)
_credentials_dependency = Depends(_bearer)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """表示已验证令牌中的最小身份和网点范围。"""

    id: UUID
    role: Role
    station_id: UUID | None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = _credentials_dependency,
) -> CurrentUser:
    """从 Bearer JWT 构造当前用户，拒绝缺失或无效凭证。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要有效的登录凭证",
        )
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = UUID(_claim_as_string(claims, "sub"))
        role = Role(_claim_as_string(claims, "role"))
        station_value = claims.get("station_id")
        station_id = UUID(station_value) if isinstance(station_value, str) else None
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证无效",
        ) from error
    return CurrentUser(id=user_id, role=role, station_id=station_id)


def _claim_as_string(claims: dict[str, object], name: str) -> str:
    """读取并校验 JWT 字符串声明。"""
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"JWT 声明无效: {name}")
    return value


def require_roles(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    """返回角色依赖，当前用户角色不在允许列表时拒绝访问。"""
    def dependency(current_user: CurrentUser) -> CurrentUser:
        if current_user.role not in roles:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="角色权限不足",
                status_code=403,
            )
        return current_user

    return dependency


def require_station_scope(
    station_id: UUID, current_user: CurrentUser
) -> CurrentUser:
    """校验当前用户是否属于指定网点范围。"""
    if current_user.station_id != station_id:
        raise AppError(
            code="FORBIDDEN_STATION_SCOPE",
            message="网点范围不足",
            status_code=403,
        )
    return current_user


def require_resource_owner(resource_owner_id: UUID, current_user: CurrentUser) -> None:
    """确保客户只能访问自己拥有的资源。"""
    if current_user.role is Role.CUSTOMER and resource_owner_id != current_user.id:
        raise AppError(
            code="FORBIDDEN_RESOURCE_OWNER",
            message="只能访问本人资源",
            status_code=403,
        )
