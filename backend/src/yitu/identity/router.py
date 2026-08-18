from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role, User
from yitu.identity.security import (
    create_access_token,
    hash_password,
    is_valid_phone,
    normalize_phone,
    verify_password,
)
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.config import get_settings
from yitu.platform.database import get_session
from yitu.platform.errors import AppError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_session_dependency = Depends(get_session)
_current_user_dependency = Depends(get_current_user)


class DemoLoginRequest(BaseModel):
    """演示登录请求。"""

    login_name: str
    password: str


class AuthTokenResponse(BaseModel):
    """登录/注册响应，只返回访问令牌和类型。"""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """客户注册请求。"""

    phone: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    """手机号登录请求。"""

    phone: str
    password: str


class CurrentUserResponse(BaseModel):
    """当前用户的最小公开身份信息。"""

    id: UUID
    display_name: str
    role: Role
    station_id: UUID | None


@router.post("/demo-login", response_model=AuthTokenResponse)
async def demo_login(
    request: DemoLoginRequest,
    session: AsyncSession = _session_dependency,
) -> AuthTokenResponse:
    """仅在演示配置下使用账号密码签发访问令牌。"""
    if get_settings().app_profile != "demo":
        raise AppError(
            code="NOT_FOUND",
            message="接口不存在",
            status_code=404,
        )
    user = (
        await session.execute(
            select(User).where(User.login_name == request.login_name)
        )
    ).scalar_one_or_none()
    if user is None or not verify_password(request.password, user.password_hash):
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="账号或密码错误",
            status_code=401,
        )
    role_value = user.role.value if isinstance(user.role, Role) else str(user.role)
    return AuthTokenResponse(
        access_token=create_access_token(user.id, role_value, user.station_id),
    )


@router.post("/register", response_model=AuthTokenResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = _session_dependency,
) -> AuthTokenResponse:
    """注册客户账号并直接签发访问令牌（注册即登录）。"""
    phone = normalize_phone(request.phone)
    if not is_valid_phone(request.phone):
        raise AppError(
            code="INVALID_PHONE",
            message="手机号格式不正确",
            status_code=422,
        )
    if len(request.password) < 8:
        raise AppError(
            code="WEAK_PASSWORD",
            message="密码至少 8 位",
            status_code=422,
        )
    existing = (
        await session.execute(
            select(User).where(or_(User.phone == phone, User.login_name == phone))
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            code="PHONE_ALREADY_REGISTERED",
            message="该手机号已注册",
            status_code=409,
        )
    user = User(
        login_name=phone,
        phone=phone,
        display_name=(request.display_name or "").strip() or f"用户{phone[-4:]}",
        password_hash=hash_password(request.password),
        role=Role.CUSTOMER,
        demo_key=None,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AppError(
            code="PHONE_ALREADY_REGISTERED",
            message="该手机号已注册",
            status_code=409,
        ) from error
    return AuthTokenResponse(
        access_token=create_access_token(user.id, Role.CUSTOMER.value, user.station_id),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = _session_dependency,
) -> AuthTokenResponse:
    """手机号密码登录，签发访问令牌。"""
    phone = normalize_phone(request.phone)
    user = (
        await session.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    if user is None or not verify_password(request.password, user.password_hash):
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="手机号或密码错误",
            status_code=401,
        )
    role_value = user.role.value if isinstance(user.role, Role) else str(user.role)
    return AuthTokenResponse(
        access_token=create_access_token(user.id, role_value, user.station_id),
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    current_user: CurrentUser = _current_user_dependency,
    session: AsyncSession = _session_dependency,
) -> CurrentUserResponse:
    """返回当前令牌对应的用户公开信息。"""
    user = await session.get(User, current_user.id)
    if user is None:
        raise AppError(
            code="USER_NOT_FOUND",
            message="用户不存在",
            status_code=401,
        )
    return CurrentUserResponse(
        id=user.id,
        display_name=user.display_name,
        role=user.role,
        station_id=user.station_id,
    )
