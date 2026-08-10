"""不可变支付流水模型。"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class PaymentTransaction(Base):
    """保存支付、补差价和退款事实，禁止覆盖历史金额。"""

    __tablename__ = "payment_transactions"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_payment_transactions_owner_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    quote_id: Mapped[UUID | None] = mapped_column(ForeignKey("quote_snapshots.id", ondelete="RESTRICT"), nullable=True)
    shipment_id: Mapped[UUID | None] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=True)
    related_transaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("payment_transactions.id", ondelete="RESTRICT"), nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
