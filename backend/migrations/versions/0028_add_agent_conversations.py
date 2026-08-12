"""新增可恢复的 Agent 会话和消息。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建按用户隔离的会话以及可用于 SSE 游标的持久化消息。"""
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_conversations_owner_updated",
        "agent_conversations",
        ["owner_id", "updated_at"],
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_conversation_created",
        "agent_messages",
        ["conversation_id", "created_at", "id"],
    )


def downgrade() -> None:
    """删除 Agent 消息和会话。"""
    op.drop_index(
        "ix_agent_messages_conversation_created", table_name="agent_messages"
    )
    op.drop_table("agent_messages")
    op.drop_index(
        "ix_agent_conversations_owner_updated", table_name="agent_conversations"
    )
    op.drop_table("agent_conversations")
