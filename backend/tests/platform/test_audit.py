from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.database import SessionFactory


class FixedClock(Clock):
    @staticmethod
    def now() -> datetime:
        return datetime(2026, 8, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


async def test_audit_service_records_immutable_complete_entry() -> None:
    request_id = str(uuid4())

    async with SessionFactory() as session, session.begin():
        entry = await AuditService(session, clock=FixedClock()).record(
            actor="user:U001",
            action="shipment.cancel",
            resource="shipment:S001",
            before_summary={"status": "CREATED"},
            after_summary={"status": "CANCELLED"},
            reason="客户申请取消",
            request_id=request_id,
        )

    assert entry.actor == "user:U001"
    assert entry.action == "shipment.cancel"
    assert entry.resource == "shipment:S001"
    assert entry.before_summary == {"status": "CREATED"}
    assert entry.after_summary == {"status": "CANCELLED"}
    assert entry.reason == "客户申请取消"
    assert entry.request_id == request_id
    assert entry.created_at.isoformat() == "2026-08-09T14:30:00+08:00"
    with pytest.raises(FrozenInstanceError):
        cast(Any, entry).reason = "篡改原因"
    assert not hasattr(AuditService, "update")


async def test_audit_service_always_appends_history() -> None:
    resource = f"shipment:{uuid4()}"

    async with SessionFactory() as session, session.begin():
        service = AuditService(session, clock=FixedClock())
        first = await service.record(
            actor="user:U001",
            action="shipment.create",
            resource=resource,
            before_summary=None,
            after_summary={"status": "CREATED"},
            reason=None,
            request_id=str(uuid4()),
        )
        second = await service.record(
            actor="user:U001",
            action="shipment.cancel",
            resource=resource,
            before_summary={"status": "CREATED"},
            after_summary={"status": "CANCELLED"},
            reason="客户申请取消",
            request_id=str(uuid4()),
        )

    async with SessionFactory() as session:
        actions = (
            await session.execute(
                text(
                    "SELECT action FROM audit_entries "
                    "WHERE resource = :resource ORDER BY id"
                ),
                {"resource": resource},
            )
        ).scalars().all()

    assert first.id != second.id
    assert actions == ["shipment.create", "shipment.cancel"]


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
