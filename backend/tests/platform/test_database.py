from datetime import datetime

import pytest

from yitu.platform.config import Settings
from yitu.platform.database import (
    SessionFactory,
    dispose_database,
    get_session,
    transactional_session,
)


def test_settings_rejects_non_business_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YITU_BUSINESS_TIMEZONE", "UTC")

    with pytest.raises(ValueError):
        Settings()


async def test_connection_uses_business_timezone() -> None:
    sessions = get_session()
    session = await anext(sessions)

    try:
        connection = await session.connection()
        timezone = (
            await connection.exec_driver_sql("SHOW TIME ZONE")
        ).scalar_one()
    finally:
        await sessions.aclose()

    assert timezone == "Asia/Shanghai"


async def test_database_now_is_timezone_aware() -> None:
    async with SessionFactory() as session:
        connection = await session.connection()
        current_time = (
            await connection.exec_driver_sql("SELECT now()")
        ).scalar_one()

    assert isinstance(current_time, datetime)
    assert current_time.tzinfo is not None
    assert current_time.utcoffset() is not None


async def test_transaction_rolls_back_on_exception() -> None:
    async with SessionFactory() as session:
        connection = await session.connection()
        await connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS test_transaction_probe "
            "(id integer PRIMARY KEY)"
        )
        await connection.exec_driver_sql("TRUNCATE TABLE test_transaction_probe")
        await session.commit()

    try:
        with pytest.raises(RuntimeError, match="force rollback"):
            async with transactional_session() as session:
                connection = await session.connection()
                await connection.exec_driver_sql(
                    "INSERT INTO test_transaction_probe (id) VALUES (1)"
                )
                raise RuntimeError("force rollback")

        async with SessionFactory() as session:
            connection = await session.connection()
            row_count = (
                await connection.exec_driver_sql(
                    "SELECT count(*) FROM test_transaction_probe"
                )
            ).scalar_one()

        assert row_count == 0
    finally:
        async with SessionFactory() as session:
            connection = await session.connection()
            await connection.exec_driver_sql("DROP TABLE test_transaction_probe")
            await session.commit()


async def test_pgvector_extension_is_available() -> None:
    async with SessionFactory() as session:
        connection = await session.connection()
        extension_version = (
            await connection.exec_driver_sql(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
        ).scalar_one_or_none()

    assert extension_version is not None


async def test_dispose_database_closes_pooled_connections() -> None:
    async with SessionFactory() as session:
        connection = await session.connection()
        backend_pid = (
            await connection.exec_driver_sql("SELECT pg_backend_pid()")
        ).scalar_one()

    await dispose_database()

    async with SessionFactory() as session:
        connection = await session.connection()
        active_connection_count = (
            await connection.exec_driver_sql(
                "SELECT count(*) FROM pg_stat_activity "
                f"WHERE pid = {backend_pid}"
            )
        ).scalar_one()

    assert active_connection_count == 0
