from uuid import UUID

from pydantic import BaseModel, ConfigDict

from yitu.regions.models import RegionLevel


class RegionView(BaseModel):
    """前端下拉框所需的最小行政区划信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    level: RegionLevel


class RegionListResponse(BaseModel):
    items: list[RegionView]
