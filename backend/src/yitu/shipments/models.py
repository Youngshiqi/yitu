from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base
from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus


class Shipment(Base):
    """保存运单创建时的地址快照和履约方式。"""

    __tablename__ = "shipments"

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
