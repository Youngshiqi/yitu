"""Agent 会话和消息持久化模型。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class AgentConversation(Base):
    """保存一个用户独占、可在进程重启后恢复的 Agent 会话。"""

    __tablename__ = "agent_conversations"
    __table_args__ = (
        Index("ix_agent_conversations_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentMessage(Base):
    """保存会话消息及其结构化工具信封，不在日志中复制正文。"""

    __tablename__ = "agent_messages"
    __table_args__ = (
        Index(
            "ix_agent_messages_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    envelope: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentShipmentDraft(Base):
    """保存当前会话唯一的运单草稿快照和报价绑定。"""

    __tablename__ = "agent_shipment_drafts"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_agent_shipment_drafts_conversation"),
        Index("ix_agent_shipment_drafts_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INCOMPLETE")
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    quote_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("quote_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    quote_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentActionGrant(Base):
    """保存一次性敏感动作授权，授权内容与草稿和报价版本绑定。"""

    __tablename__ = "agent_action_grants"
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_agent_action_grants_nonce"),
        Index("ix_agent_action_grants_owner_expires", "owner_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_shipment_drafts.id", ondelete="CASCADE"), nullable=False
    )
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_id: Mapped[UUID] = mapped_column(
        ForeignKey("quote_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    quote_version: Mapped[str] = mapped_column(String(64), nullable=False)
    command_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    command_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentMemory(Base):
    """保存用户明确确认的持久记忆；原始消息和敏感信息不进入该表。"""

    __tablename__ = "agent_memories"
    __table_args__ = (Index("ix_agent_memories_owner_active", "owner_id", "active"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
