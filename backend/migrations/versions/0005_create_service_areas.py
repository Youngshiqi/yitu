"""创建服务区域映射并写入确定性演示网点。"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATIONS = (
    ("10000000-0000-4000-8000-000000000001", "BJS-001", "北京朝阳网点", "110101"),
    ("10000000-0000-4000-8000-000000000002", "SHS-001", "上海虹桥网点", "310105"),
    ("10000000-0000-4000-8000-000000000003", "GZS-001", "广州天河网点", "440106"),
    ("10000000-0000-4000-8000-000000000004", "SZS-001", "深圳南山网点", "440305"),
)
_AREAS = (
    ("110101", "HOME_PICKUP", "10000000-0000-4000-8000-000000000001"),
    ("310105", "HOME_PICKUP", "10000000-0000-4000-8000-000000000002"),
    ("440106", "HOME_PICKUP", "10000000-0000-4000-8000-000000000003"),
    ("440305", "HOME_PICKUP", "10000000-0000-4000-8000-000000000004"),
    ("310105", "STATION_DROP_OFF", "10000000-0000-4000-8000-000000000002"),
)


def upgrade() -> None:
    """创建服务区域表并写入演示网点和映射。"""
    op.create_table(
        "service_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("district_code", sa.String(length=12), nullable=False),
        sa.Column("service_type", sa.String(length=32), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["station_id"], ["stations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "district_code", "service_type", name="uq_service_areas_lookup"
        ),
    )
    stations = sa.table(
        "stations",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("district_code", sa.String()),
    )
    op.bulk_insert(
        stations,
        [
            {
                "id": UUID(station_id),
                "code": code,
                "name": name,
                "district_code": district_code,
            }
            for station_id, code, name, district_code in _STATIONS
        ],
    )
    areas = sa.table(
        "service_areas",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("district_code", sa.String()),
        sa.column("service_type", sa.String()),
        sa.column("station_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
    )
    op.bulk_insert(
        areas,
        [
            {
                "id": UUID(f"20000000-0000-4000-8000-{index:012d}"),
                "district_code": district_code,
                "service_type": service_type,
                "station_id": UUID(station_id),
                "version": 1,
            }
            for index, (district_code, service_type, station_id) in enumerate(
                _AREAS, start=1
            )
        ],
    )


def downgrade() -> None:
    """删除服务区域映射并清理本迁移写入的演示网点。"""
    op.drop_table("service_areas")
    op.execute(
        "UPDATE users SET station_id = NULL "
        "WHERE station_id IN ("
        "SELECT id FROM stations WHERE code IN "
        "('BJS-001', 'SHS-001', 'GZS-001', 'SZS-001')"
        ")"
    )
    stations = sa.table("stations", sa.column("code", sa.String()))
    op.execute(
        stations.delete().where(
            stations.c.code.in_([code for _, code, _, _ in _STATIONS])
        )
    )
