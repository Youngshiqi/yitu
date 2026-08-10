"""修正价格规则生效时间的时区类型。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column_name in ("effective_from", "effective_to"):
        op.alter_column(
            "pricing_rules",
            column_name,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column_name} AT TIME ZONE 'Asia/Shanghai'",
        )


def downgrade() -> None:
    for column_name in ("effective_to", "effective_from"):
        op.alter_column(
            "pricing_rules",
            column_name,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{column_name} AT TIME ZONE 'Asia/Shanghai'",
        )
