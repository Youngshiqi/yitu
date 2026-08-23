from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus


class Shipment(Base):
    """保存运单创建时的地址快照和履约方式。"""

    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("package_id", name="uq_shipments_package"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    sender_address_id: Mapped[UUID | None] = mapped_column(ForeignKey("addresses.id", ondelete="RESTRICT"), nullable=True)
    receiver_address_id: Mapped[UUID | None] = mapped_column(ForeignKey("addresses.id", ondelete="RESTRICT"), nullable=True)
    origin_station_id: Mapped[UUID | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True)
    destination_station_id: Mapped[UUID | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True)
    pickup_method: Mapped[PickupMethod] = mapped_column(String(32), nullable=False)
    delivery_method: Mapped[DeliveryMethod] = mapped_column(String(32), nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(String(32), nullable=False)
    quote_id: Mapped[UUID | None] = mapped_column(ForeignKey("quote_snapshots.id", ondelete="RESTRICT"), nullable=True)
    package_id: Mapped[UUID | None] = mapped_column(ForeignKey("shipment_packages.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShipmentPackage(Base):
    """保存一票运单唯一包裹的申报、复重和特殊要求。"""

    __tablename__ = "shipment_packages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_weight_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_length_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_width_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_height_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_value_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_width_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reweighed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reweighed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
