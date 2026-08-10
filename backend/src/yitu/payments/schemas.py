"""支付 HTTP 输入输出模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PayRequest(BaseModel):
    """报价支付请求。"""

    shipment_id: UUID
    amount_cents: int = Field(gt=0)


class SupplementRequest(PayRequest):
    """复重补差价请求。"""


class PaymentTransactionView(BaseModel):
    """支付流水公开视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    quote_id: UUID | None
    shipment_id: UUID | None
    related_transaction_id: UUID | None
    transaction_type: str
    status: str
    amount_cents: int
    created_at: datetime
