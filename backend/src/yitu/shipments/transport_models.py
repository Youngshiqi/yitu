import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class TransportLegStatus(str, enum.Enum):
    """模拟运输段状态。"""

    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"


class TransportLeg(Base):
    """保存始发网点到目标网点的模拟干线段。"""

    __tablename__ = "transport_legs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    origin_station_id: Mapped[UUID] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    destination_station_id: Mapped[UUID | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[TransportLegStatus] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
