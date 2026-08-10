"""计价 HTTP 输入输出模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yitu.shipments.enums import DeliveryMethod, PickupMethod


class QuoteRequest(BaseModel):
    """客户报价请求。"""

    origin_district_code: str = Field(min_length=6, max_length=6)
    destination_district_code: str = Field(min_length=6, max_length=6)
    pickup_method: PickupMethod
    delivery_method: DeliveryMethod
    actual_weight_grams: int = Field(gt=0)
    length_cm: int = Field(gt=0)
    width_cm: int = Field(gt=0)
    height_cm: int = Field(gt=0)
    declared_value_cents: int = Field(default=0, ge=0)


class ReweighRequest(BaseModel):
    """复重请求，只允许更新包裹尺寸和重量。"""

    actual_weight_grams: int = Field(gt=0)
    length_cm: int = Field(gt=0)
    width_cm: int = Field(gt=0)
    height_cm: int = Field(gt=0)


class QuoteView(BaseModel):
    """报价快照公开视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    rule_version: str
    input_snapshot: dict[str, object]
    fee_items: list[dict[str, object]]
    volume_weight_grams: int
    billable_weight_grams: int
    total_cents: int
    created_at: datetime
