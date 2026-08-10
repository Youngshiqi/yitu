from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TrackingEventView(BaseModel):
    """面向客户展示的轨迹事件。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence_no: int
    event_type: str
    message: str
    visible_to_customer: bool
    occurred_at: datetime
