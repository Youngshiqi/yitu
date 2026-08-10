"""运单履约冻结事实。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base
from yitu.shipments.enums import ShipmentStatus


class ShipmentHold(Base):
    """保存异常等来源对运单履约推进的活动阻断。"""

    __tablename__ = "shipment_holds"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_shipment_holds_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    frozen_status: Mapped[ShipmentStatus] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    placed_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    place_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    release_idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
