"""修正报价快照创建时间的时区类型。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "quote_snapshots",
        "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'Asia/Shanghai'",
    )


def downgrade() -> None:
    op.alter_column(
        "quote_snapshots",
        "created_at",
        type_=sa.DateTime(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'Asia/Shanghai'",
    )
