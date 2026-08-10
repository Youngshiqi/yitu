"""恢复与退回动作事实。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base
from yitu.returns.enums import RecoveryAction, RecoveryStatus


class RecoveryCase(Base):
    """记录任务六每次命名恢复动作的审计事实。"""

    __tablename__ = "recovery_cases"
    __table_args__ = (
        UniqueConstraint(
            "shipment_id",
            "action",
            "idempotency_key",
            name="uq_recovery_cases_shipment_action_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[RecoveryAction] = mapped_column(String(32), nullable=False)
    status: Mapped[RecoveryStatus] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
