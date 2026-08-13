"""增加网点启停状态和运营管理时间字段。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为现有网点补齐可管理状态，并补充派送服务映射。"""
    op.add_column(
        "stations",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "stations",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "stations",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # 早期演示数据只配置了上门取件。地址派送使用独立服务类型后，
    # 为已有覆盖区县补齐送货上门能力，保证旧网点仍可创建运单。
    op.execute(
        """
        INSERT INTO service_areas (id, district_code, service_type, station_id, version)
        SELECT gen_random_uuid(), district_code, 'HOME_DELIVERY', station_id, version
        FROM service_areas source
        WHERE source.service_type = 'HOME_PICKUP'
          AND NOT EXISTS (
            SELECT 1 FROM service_areas target
            WHERE target.district_code = source.district_code
              AND target.service_type = 'HOME_DELIVERY'
          )
        """
    )


def downgrade() -> None:
    """移除网点运营管理字段。"""
    op.execute("DELETE FROM service_areas WHERE service_type = 'HOME_DELIVERY'")
    op.drop_column("stations", "updated_at")
    op.drop_column("stations", "created_at")
    op.drop_column("stations", "enabled")
