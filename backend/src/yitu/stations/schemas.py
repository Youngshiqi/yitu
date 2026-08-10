from uuid import UUID

from pydantic import BaseModel


class StationResponse(BaseModel):
    id: UUID
    code: str
    name: str
    district_code: str
    model_config = {"from_attributes": True}
