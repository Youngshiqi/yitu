"""运单新增 created_at：支持按下单时间排序并在详情展示创建时间。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shipments",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE shipments SET created_at = now() WHERE created_at IS NULL")
    op.alter_column("shipments", "created_at", nullable=False)


def downgrade() -> None:
    op.drop_column("shipments", "created_at")
