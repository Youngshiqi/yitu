"""SLA 规则、阶段实例和暂停记录。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class SLARule(Base):
    """可版本化的 SLA 规则。"""

    __tablename__ = "sla_rules"
    __table_args__ = (UniqueConstraint("version", "route_code", "stage", name="uq_sla_rules_version_route_stage"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False, default="STANDARD")
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    target_work_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_natural_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)


class SLAInstance(Base):
    """运单某个履约阶段的 SLA 快照。"""

    __tablename__ = "sla_instances"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("sla_rules.id", ondelete="RESTRICT"), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promised_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    breached: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_scan_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SLAPause(Base):
    """SLA 阶段暂停区间。"""

    __tablename__ = "sla_pauses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("sla_instances.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
