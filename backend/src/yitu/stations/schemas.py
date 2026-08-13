from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ServiceType(StrEnum):
    """网点可以覆盖的四类收寄服务。"""

    HOME_PICKUP = "HOME_PICKUP"
    STATION_DROP_OFF = "STATION_DROP_OFF"
    HOME_DELIVERY = "HOME_DELIVERY"
    STATION_PICKUP = "STATION_PICKUP"


class StationResponse(BaseModel):
    id: UUID
    code: str
    name: str
    district_code: str
    model_config = ConfigDict(from_attributes=True)


class ServiceAreaInput(BaseModel):
    district_region_id: UUID
    service_types: list[ServiceType] = Field(min_length=1)


class StationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    district_region_id: UUID
    service_areas: list[ServiceAreaInput] = Field(default_factory=list)


class StationUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    district_region_id: UUID | None = None
    service_areas: list[ServiceAreaInput] | None = None


class ServiceAreaView(BaseModel):
    province_region_id: UUID
    city_region_id: UUID
    district_region_id: UUID
    district_code: str
    district_name: str
    province_name: str
    city_name: str
    service_types: list[ServiceType]


class StationAdminView(BaseModel):
    id: UUID
    code: str
    name: str
    district_code: str
    province_region_id: UUID
    city_region_id: UUID
    district_region_id: UUID
    district_name: str
    province_name: str
    city_name: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    service_areas: list[ServiceAreaView]


class StationAdminList(BaseModel):
    items: list[StationAdminView]
    total: int
