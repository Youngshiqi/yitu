"""Add knowledge parsing metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("parsed_text", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("parser_name", sa.String(64), nullable=True))
    op.add_column("knowledge_documents", sa.Column("parser_version", sa.String(32), nullable=True))
    op.add_column("knowledge_documents", sa.Column("parse_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("knowledge_documents", "parse_attempts")
    op.drop_column("knowledge_documents", "parser_version")
    op.drop_column("knowledge_documents", "parser_name")
    op.drop_column("knowledge_documents", "parsed_text")
