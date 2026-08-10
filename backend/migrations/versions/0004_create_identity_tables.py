"""创建阶段二身份和网点基础表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建网点和用户身份表。"""
    role_values = (
        "CUSTOMER",
        "COURIER",
        "STATION_OPERATOR",
        "OPERATIONS_ADMIN",
        "SYSTEM_ADMIN",
    )
    op.create_table(
        "stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("district_code", sa.String(length=12), nullable=False),
        sa.UniqueConstraint("code", name="uq_stations_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("login_name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("demo_key", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["station_id"], ["stations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("login_name", name="uq_users_login_name"),
        sa.UniqueConstraint("demo_key", name="uq_users_demo_key"),
        sa.CheckConstraint(
            "role IN (" + ",".join(f"'{value}'" for value in role_values) + ")",
            name="ck_users_role",
        ),
    )


def downgrade() -> None:
    """按外键依赖顺序删除用户和网点表。"""
    op.drop_table("users")
    op.drop_table("stations")
