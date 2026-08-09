from sqlalchemy import text

from yitu.platform.database import SessionFactory


async def test_audit_entries_has_required_postgresql_columns() -> None:
    async with SessionFactory() as session:
        columns = (
            await session.execute(
                text(
                    "SELECT column_name, data_type, udt_name, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'audit_entries' "
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
        },
        {
            "column_name": "actor",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
        },
        {
            "column_name": "action",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
        },
        {
            "column_name": "resource",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
        },
        {
            "column_name": "before_summary",
            "data_type": "jsonb",
            "udt_name": "jsonb",
            "is_nullable": "YES",
        },
        {
            "column_name": "after_summary",
            "data_type": "jsonb",
            "udt_name": "jsonb",
            "is_nullable": "YES",
        },
        {
            "column_name": "reason",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "YES",
        },
        {
            "column_name": "request_id",
            "data_type": "character varying",
            "udt_name": "varchar",
            "is_nullable": "NO",
        },
        {
            "column_name": "created_at",
            "data_type": "timestamp with time zone",
            "udt_name": "timestamptz",
            "is_nullable": "NO",
        },
    ]
