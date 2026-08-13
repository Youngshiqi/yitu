from uuid import UUID

from pydantic import BaseModel, Field


class AddressCreate(BaseModel):
    """客户端提交地址时只引用后端下发的行政区域 ID。"""

    label: str | None = Field(default=None, max_length=32)
    recipient_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=32)
    province_region_id: UUID
    city_region_id: UUID
    district_region_id: UUID
    detail: str = Field(min_length=1, max_length=256)


class AddressUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=32)
    recipient_name: str | None = Field(default=None, min_length=1, max_length=128)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    province_region_id: UUID | None = None
    city_region_id: UUID | None = None
    district_region_id: UUID | None = None
    detail: str | None = Field(default=None, min_length=1, max_length=256)


class AddressResponse(BaseModel):
    id: UUID
    label: str | None
    recipient_name: str
    phone: str
    province_region_id: UUID
    province_name: str
    city_region_id: UUID
    city_name: str
    district_region_id: UUID
    district_name: str
    detail: str
    full_address: str
