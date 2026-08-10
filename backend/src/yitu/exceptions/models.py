"""异常工单和任务重派事实。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yitu.exceptions.enums import (
    ExceptionSeverity,
    ExceptionSourceType,
    ExceptionStatus,
    ExceptionType,
    ResolutionCode,
)
from yitu.platform.models import Base


class ExceptionCase(Base):
    """独立保存一张可审计异常工单。"""

    __tablename__ = "exception_cases"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_exception_cases_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_type: Mapped[ExceptionType] = mapped_column(String(32), nullable=False)
    severity: Mapped[ExceptionSeverity] = mapped_column(String(32), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(String(32), nullable=False)
    source_type: Mapped[ExceptionSourceType] = mapped_column(
        String(32),
        nullable=False,
    )
    source_id: Mapped[UUID | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    blocks_fulfillment: Mapped[bool] = mapped_column(nullable=False, default=False)
    frozen_shipment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reported_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    responsible_station_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolution_code: Mapped[ResolutionCode | None] = mapped_column(
        String(64),
        nullable=True,
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)


class ExceptionTaskReassignment(Base):
    """异常处理过程中关闭旧任务并创建替代任务的事实。"""

    __tablename__ = "exception_task_reassignments"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "old_task_id",
            "idempotency_key",
            name="uq_exception_task_reassignments_case_old_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("exception_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("courier_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    new_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("courier_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
