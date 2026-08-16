"""Correct the district code for the Beijing station."""

from collections.abc import Sequence

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE stations SET name = '北京东城网点', district_code = '110101' "
        "WHERE code = 'BJS-001'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE stations SET name = '北京朝阳网点', district_code = '110101' "
        "WHERE code = 'BJS-001'"
    )
