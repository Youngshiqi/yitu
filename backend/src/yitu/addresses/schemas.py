from uuid import UUID

from pydantic import BaseModel


class AddressCreate(BaseModel):
    label: str | None = None
    recipient_name: str
    phone: str
    district_code: str
    detail: str

class AddressUpdate(BaseModel):
    label: str | None = None
    recipient_name: str | None = None
    phone: str | None = None
    district_code: str | None = None
    detail: str | None = None

class AddressResponse(AddressCreate):
    id: UUID
    model_config = {"from_attributes": True}
