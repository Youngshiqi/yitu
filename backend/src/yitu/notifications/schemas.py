"""通知接口模型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationView(BaseModel):
    """通知事实视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    template_code: str
    template_data: dict[str, object]
    title: str
    content: str
    status: str
    created_at: datetime
    read_at: datetime | None
