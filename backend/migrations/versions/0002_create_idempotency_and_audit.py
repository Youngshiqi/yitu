"""建立幂等与审计记录表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建用于可靠重放和追加式审计的持久化表。"""
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(request_hash) = 64 "
            "AND request_hash ~ '^[0-9A-Fa-f]{64}$'",
            name="ck_idempotency_records_request_hash_sha256",
        ),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_records_scope_key"),
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("before_summary", postgresql.JSONB(), nullable=True),
        sa.Column("after_summary", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """按创建顺序的反向删除表，确保回退安全。"""
    op.drop_table("audit_entries")
    op.drop_table("idempotency_records")
