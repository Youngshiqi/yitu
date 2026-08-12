"""新增 Agent 运单草稿快照。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建会话唯一草稿并绑定可失效报价。"""
    op.create_table(
        "agent_shipment_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=True),
        sa.Column("quote_version", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quote_id"], ["quote_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_agent_shipment_drafts_conversation"),
    )
    op.create_index(
        "ix_agent_shipment_drafts_owner_updated",
        "agent_shipment_drafts",
        ["owner_id", "updated_at"],
    )


def downgrade() -> None:
    """删除 Agent 运单草稿。"""
    op.drop_index("ix_agent_shipment_drafts_owner_updated", table_name="agent_shipment_drafts")
    op.drop_table("agent_shipment_drafts")
