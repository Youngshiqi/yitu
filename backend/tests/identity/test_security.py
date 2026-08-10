from datetime import timedelta

import pytest

from yitu.identity.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_one_way_and_verifiable() -> None:
    password = "演示密码-不要记录"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash) is True
    assert verify_password("错误密码", password_hash) is False


def test_access_token_contains_identity_claims() -> None:
    token = create_access_token("user-001", "CUSTOMER", None)

    claims = decode_access_token(token)

    assert claims["sub"] == "user-001"
    assert claims["role"] == "CUSTOMER"
    assert claims["station_id"] is None
    assert claims["exp"]


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(
        "user-001",
        "CUSTOMER",
        None,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(ValueError, match="令牌无效或已过期"):
        decode_access_token(token)
