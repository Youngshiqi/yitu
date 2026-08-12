"""新增 Agent 敏感写动作的一次性授权表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保存授权快照，供并发安全的一次性消费。"""
    op.create_table(
        "agent_action_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("draft_id", sa.UUID(), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("quote_version", sa.String(length=64), nullable=False),
        sa.Column("command_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["draft_id"], ["agent_shipment_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quote_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce", name="uq_agent_action_grants_nonce"),
    )
    op.create_index(
        "ix_agent_action_grants_owner_expires",
        "agent_action_grants",
        ["owner_id", "expires_at"],
    )


def downgrade() -> None:
    """删除 Agent 敏感动作授权表。"""
    op.drop_index("ix_agent_action_grants_owner_expires", table_name="agent_action_grants")
    op.drop_table("agent_action_grants")
