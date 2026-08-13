"""建立版本化行政区划并关联地址。"""

import json
from collections.abc import Sequence
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _region_id(level: str, code: str) -> str:
    """同一版本数据在所有环境生成稳定主键。"""
    return str(uuid5(NAMESPACE_URL, f"yitu:cn-region:{level}:{code}"))


def _load_regions() -> tuple[str, list[dict[str, object]]]:
    path = Path(__file__).resolve().parents[2] / "data" / "regions" / "cn-regions-2022.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["version"]), list(payload["regions"])


def upgrade() -> None:
    """创建区域表、导入固定版本数据并回填已有地址。"""
    op.create_table(
        "administrative_regions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("data_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["administrative_regions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("level", "code", name="uq_regions_level_code"),
    )
    op.create_index(
        "ix_regions_parent_enabled", "administrative_regions", ["parent_id", "enabled"]
    )

    version, regions = _load_regions()
    table = sa.table(
        "administrative_regions",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("level", sa.String()),
        sa.column("parent_id", sa.UUID()),
        sa.column("enabled", sa.Boolean()),
        sa.column("data_version", sa.String()),
    )
    rows = []
    for region in regions:
        level = str(region["level"])
        code = str(region["code"])
        parent_code = region.get("parent_code")
        parent_level = {"CITY": "PROVINCE", "DISTRICT": "CITY"}.get(level)
        rows.append(
            {
                "id": _region_id(level, code),
                "code": code,
                "name": str(region["name"]),
                "level": level,
                "parent_id": (
                    _region_id(parent_level, str(parent_code))
                    if parent_code is not None and parent_level is not None
                    else None
                ),
                "enabled": True,
                "data_version": version,
            }
        )
    # 分批插入可控制单条 SQL 的参数数量。
    for index in range(0, len(rows), 500):
        op.bulk_insert(table, rows[index : index + 500])

    op.add_column("addresses", sa.Column("province_region_id", sa.UUID(), nullable=True))
    op.add_column("addresses", sa.Column("city_region_id", sa.UUID(), nullable=True))
    op.add_column("addresses", sa.Column("district_region_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_addresses_province_region", "addresses", "administrative_regions",
        ["province_region_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_addresses_city_region", "addresses", "administrative_regions",
        ["city_region_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_addresses_district_region", "addresses", "administrative_regions",
        ["district_region_id"], ["id"], ondelete="RESTRICT"
    )

    connection = op.get_bind()
    unresolved = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM addresses a
            LEFT JOIN administrative_regions d
              ON d.code = a.district_code AND d.level = 'DISTRICT'
            WHERE d.id IS NULL
            """
        )
    ).scalar_one()
    if unresolved:
        raise RuntimeError(f"存在 {unresolved} 条地址无法匹配 2022 行政区划")
    connection.execute(
        sa.text(
            """
            UPDATE addresses a
            SET district_region_id = d.id,
                city_region_id = c.id,
                province_region_id = p.id
            FROM administrative_regions d
            JOIN administrative_regions c ON c.id = d.parent_id
            JOIN administrative_regions p ON p.id = c.parent_id
            WHERE d.code = a.district_code AND d.level = 'DISTRICT'
            """
        )
    )
    op.alter_column("addresses", "province_region_id", nullable=False)
    op.alter_column("addresses", "city_region_id", nullable=False)
    op.alter_column("addresses", "district_region_id", nullable=False)


def downgrade() -> None:
    """移除地址区域关联和行政区划表。"""
    op.drop_constraint("fk_addresses_district_region", "addresses", type_="foreignkey")
    op.drop_constraint("fk_addresses_city_region", "addresses", type_="foreignkey")
    op.drop_constraint("fk_addresses_province_region", "addresses", type_="foreignkey")
    op.drop_column("addresses", "district_region_id")
    op.drop_column("addresses", "city_region_id")
    op.drop_column("addresses", "province_region_id")
    op.drop_index("ix_regions_parent_enabled", table_name="administrative_regions")
    op.drop_table("administrative_regions")
