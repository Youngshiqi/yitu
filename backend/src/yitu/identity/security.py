from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from yitu.platform.config import get_settings

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """使用 Argon2id 哈希密码，返回可持久化的哈希字符串。"""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码是否匹配，不向调用方泄露底层哈希异常。"""
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(
    user_id: str | UUID,
    role: str,
    station_id: str | UUID | None,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """创建包含身份和网点范围的 JWT 访问令牌。"""
    now = datetime.now(UTC)
    expires = now + (expires_delta or timedelta(minutes=get_settings().jwt_expire_minutes))
    payload = {
        "sub": str(user_id),
        "role": role,
        "station_id": str(station_id) if station_id is not None else None,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    """验证 JWT 并返回身份声明，失败时统一抛出中文异常。"""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "role", "exp"]},
        )
        if "station_id" not in claims:
            raise ValueError("令牌无效或已过期")
    except jwt.PyJWTError as error:
        raise ValueError("令牌无效或已过期") from error
    return claims
