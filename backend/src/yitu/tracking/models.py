from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class TrackingEvent(Base):
    """保存不可覆盖、按顺序展示的运单轨迹事实。"""

    __tablename__ = "tracking_events"
    __table_args__ = (UniqueConstraint("shipment_id", "idempotency_key", name="uq_tracking_events_idempotency"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(256), nullable=False)
    visible_to_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
