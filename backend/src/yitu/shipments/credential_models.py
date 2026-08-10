from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base
from yitu.shipments.enums import DeliveryMethod


class PickupCredential(Base):
    """保存取件码的哈希和核验状态，不保存明文取件码。"""

    __tablename__ = "pickup_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    station_id: Mapped[UUID | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProofOfDelivery(Base):
    """保存一次性签收证明，保证每个运单只生成一份。"""

    __tablename__ = "proofs_of_delivery"
    __table_args__ = (UniqueConstraint("shipment_id", name="uq_proofs_of_delivery_shipment"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    delivery_method: Mapped[DeliveryMethod] = mapped_column(String(32), nullable=False)
    signer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    station_id: Mapped[UUID | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
