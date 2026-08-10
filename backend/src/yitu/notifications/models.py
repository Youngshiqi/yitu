"""通知事实和渠道投递记录。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class NotificationMessage(Base):
    """一条由业务事件生成的用户通知事实。"""

    __tablename__ = "notification_messages"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "recipient_id",
            name="uq_notification_messages_event_recipient",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    template_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNREAD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base):
    """通知在指定渠道上的可重试投递记录。"""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "recipient_id",
            "channel",
            name="uq_notification_deliveries_event_recipient_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("notification_messages.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
