"""计价规则和报价快照模型。"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class PricingRule(Base):
    """保存带生效时间的价格规则版本。"""

    __tablename__ = "pricing_rules"
    __table_args__ = (UniqueConstraint("version", "route_code", name="uq_pricing_rules_version_route"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    route_code: Mapped[str] = mapped_column(String(32), nullable=False)
    base_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    additional_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    remote_surcharge_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_from: Mapped[datetime] = mapped_column(nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class QuoteSnapshot(Base):
    """保存报价输入、命中规则和不可变费用明细。"""

    __tablename__ = "quote_snapshots"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("pricing_rules.id", ondelete="RESTRICT"), nullable=False)
    source_quote_id: Mapped[UUID | None] = mapped_column(ForeignKey("quote_snapshots.id", ondelete="RESTRICT"), nullable=True)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    fee_items: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    volume_weight_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    billable_weight_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
