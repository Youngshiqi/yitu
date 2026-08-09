from sqlalchemy import text

from yitu.platform.database import SessionFactory


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
