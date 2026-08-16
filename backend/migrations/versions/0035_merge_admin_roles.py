"""Merge system administrator accounts into operations administrators."""

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'OPERATIONS_ADMIN' WHERE role = 'SYSTEM_ADMIN'")


def downgrade() -> None:
    pass
