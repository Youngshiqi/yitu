"""SLA HTTP 输入输出模型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SLARuleCreate(BaseModel):
    """运营人员发布 SLA 规则的请求。"""

    version: str = Field(min_length=1, max_length=64)
    route_code: str = Field(min_length=1, max_length=64)
    service_type: str = Field(default="STANDARD", min_length=1, max_length=32)
    stage: str = Field(min_length=1, max_length=32)
    target_work_hours: int | None = Field(default=None, gt=0)
    target_natural_hours: int | None = Field(default=None, gt=0)
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "SLARuleCreate":
        """一条规则只能选用一种计时方式。"""
        if (self.target_work_hours is None) == (self.target_natural_hours is None):
            raise ValueError("必须且只能设置一种 SLA 时长")
        return self


class SLAInstanceStart(BaseModel):
    """创建运单阶段 SLA 的请求。"""

    route_code: str = Field(min_length=1, max_length=64)
    stage: str = Field(min_length=1, max_length=32)
    service_type: str = Field(default="STANDARD", min_length=1, max_length=32)


class SLAPauseRequest(BaseModel):
    """暂停 SLA 的原因。"""

    reason: str = Field(min_length=1, max_length=256)


class ETAUpdateRequest(BaseModel):
    """用于演示的 ETA 预计延误量。"""

    delay_minutes: int = Field(default=0, ge=0, le=60 * 24 * 30)


class SLARuleView(BaseModel):
    """SLA 规则公开视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: str
    route_code: str
    service_type: str
    stage: str
    target_work_hours: int | None
    target_natural_hours: int | None
    effective_from: datetime
    effective_to: datetime | None
    active: bool


class SLAInstanceView(BaseModel):
    """SLA 实例公开视图。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    shipment_id: UUID
    rule_version: str
    stage: str
    status: str
    started_at: datetime | None
    promised_delivery_at: datetime | None
    eta_at: datetime | None
    completed_at: datetime | None
    paused_seconds: int
    breached: bool
