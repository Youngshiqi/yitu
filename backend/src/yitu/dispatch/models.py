import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class CourierTaskType(str, enum.Enum):
    """快递员任务的业务类型。"""

    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class CourierTaskStatus(str, enum.Enum):
    """快递员任务的当前处理状态。"""

    AVAILABLE = "AVAILABLE"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CourierTask(Base):
    """保存由快递员执行的揽收任务。"""

    __tablename__ = "courier_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False)
    station_id: Mapped[UUID] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    task_type: Mapped[CourierTaskType] = mapped_column(String(32), nullable=False)
    status: Mapped[CourierTaskStatus] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courier_tasks.id", ondelete="RESTRICT"),
        nullable=True,
    )
