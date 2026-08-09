from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)


def test_canonical_json_sha256_ignores_object_key_order() -> None:
    first_hash = canonical_json_sha256({"name": "张三", "items": [1, 2]})
    second_hash = canonical_json_sha256({"items": [1, 2], "name": "张三"})

    assert first_hash == second_hash
    assert first_hash == "ab09aef14fcd29f2d396cb15c6c95a3003aba0e8c3a68381fc6dac4af05b2c62"


async def test_idempotency_service_replays_stored_response_without_reexecuting() -> None:
    scope = f"replay-scope-{uuid4()}"
    key = f"create-shipment-{uuid4()}"
    request_hash = canonical_json_sha256({"shipment_no": "YT-001"})
    operation_call_count = 0

    async def first_operation() -> IdempotencyResponse:
        nonlocal operation_call_count
        operation_call_count += 1
        return IdempotencyResponse(
            status_code=201,
            body={"shipment_id": "shipment-001", "status": "created"},
        )

    async with SessionFactory() as session:
        service = IdempotencyService(session)
        response = await service.execute(scope, key, request_hash, first_operation)
        await session.commit()

    async def replay_operation() -> IdempotencyResponse:
        raise AssertionError("重放请求不应再次执行操作")

    async with SessionFactory() as session:
        replay_response = await IdempotencyService(session).execute(
            scope,
            key,
            request_hash,
            replay_operation,
        )

    assert response == IdempotencyResponse(
        status_code=201,
        body={"shipment_id": "shipment-001", "status": "created"},
    )
    assert replay_response == response
    assert operation_call_count == 1


async def test_idempotency_service_rejects_key_reused_with_different_request() -> None:
    scope = f"conflict-scope-{uuid4()}"
    key = f"create-shipment-{uuid4()}"

    async def first_operation() -> IdempotencyResponse:
        return IdempotencyResponse(status_code=201, body={"shipment_id": "shipment-001"})

    async with SessionFactory() as session:
        await IdempotencyService(session).execute(
            scope,
            key,
            canonical_json_sha256({"shipment_no": "YT-001"}),
            first_operation,
        )
        await session.commit()

    async def conflicting_operation() -> IdempotencyResponse:
        raise AssertionError("键冲突请求不应执行操作")

    async with SessionFactory() as session:
        with pytest.raises(AppError) as error_info:
            await IdempotencyService(session).execute(
                scope,
                key,
                canonical_json_sha256({"shipment_no": "YT-002"}),
                conflicting_operation,
            )

    assert error_info.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert error_info.value.status_code == 409
    assert error_info.value.message == "幂等键已用于不同的请求"


async def test_idempotency_records_has_required_postgresql_columns() -> None:
    async with SessionFactory() as session:
        columns = (
            await session.execute(
                text(
                    "SELECT column_name, data_type, udt_name, is_nullable, "
                    "character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'idempotency_records' "
                    "ORDER BY ordinal_position"
                )
            )
        ).mappings().all()

    assert [dict(column) for column in columns] == [
        {
            "column_name": "id",
            "data_type": "bigint",
            "udt_name": "int8",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
        {
            "column_name": "scope",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
        {
            "column_name": "key",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
        {
            "column_name": "request_hash",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
            "character_maximum_length": 64,
        },
        {
            "column_name": "status",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
        {
            "column_name": "response_status",
            "data_type": "integer",
            "udt_name": "int4",
            "is_nullable": "YES",
            "character_maximum_length": None,
        },
        {
            "column_name": "response_body",
            "data_type": "jsonb",
            "udt_name": "jsonb",
            "is_nullable": "YES",
            "character_maximum_length": None,
        },
        {
            "column_name": "created_at",
            "data_type": "timestamp with time zone",
            "udt_name": "timestamptz",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
        {
            "column_name": "updated_at",
            "data_type": "timestamp with time zone",
            "udt_name": "timestamptz",
            "is_nullable": "NO",
            "character_maximum_length": None,
        },
    ]


async def test_idempotency_records_enforces_scope_and_key_uniqueness() -> None:
    async with SessionFactory() as session:
        constraints = (
            await session.execute(
                text(
                    "SELECT pg_get_constraintdef(constraint_row.oid) AS definition "
                    "FROM pg_constraint AS constraint_row "
                    "JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'public' "
                    "AND relation.relname = 'idempotency_records' "
                    "AND constraint_row.contype = 'u'"
                )
            )
        ).scalars().all()

    assert constraints == ["UNIQUE (scope, key)"]


@pytest.mark.parametrize("request_hash", ["g" * 64, "a" * 63])
async def test_idempotency_records_rejects_invalid_request_hash(
    request_hash: str,
) -> None:
    async with SessionFactory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO idempotency_records ("
                    "scope, key, request_hash, status, created_at, updated_at"
                    ") VALUES ("
                    ":scope, :key, :request_hash, 'completed', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "scope": f"request-hash-check-{uuid4()}",
                    "key": "create-shipment",
                    "request_hash": request_hash,
                },
            )
