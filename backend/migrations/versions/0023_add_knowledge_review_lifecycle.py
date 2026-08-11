"""Add knowledge review and publication lifecycle fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("category", sa.String(64), nullable=True))
    op.create_foreign_key("fk_knowledge_documents_reviewed_by", "knowledge_documents", "users", ["reviewed_by"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_documents_reviewed_by", "knowledge_documents", type_="foreignkey")
    for name in ("category", "effective_to", "effective_from", "published_at", "reviewed_at", "reviewed_by"):
        op.drop_column("knowledge_documents", name)
