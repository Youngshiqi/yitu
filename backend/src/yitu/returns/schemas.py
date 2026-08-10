from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yitu.returns.enums import RecoveryAction, RecoveryStatus
from yitu.shipments.enums import ShipmentStatus


class RecoveryCommand(BaseModel):
    """恢复动作通用请求。"""

    reason: str = Field(min_length=1, max_length=1000)


class RecoveryView(BaseModel):
    """恢复动作公开视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shipment_id: UUID
    action: RecoveryAction
    status: RecoveryStatus
    reason: str
    actor_id: UUID
    created_at: datetime
    completed_at: datetime | None


class RecoveryShipmentView(BaseModel):
    """动作完成后的运单与恢复事实。"""

    shipment_id: UUID
    shipment_status: ShipmentStatus
    recovery: RecoveryView
    refund_amount_cents: int = 0
    new_task_id: UUID | None = None
