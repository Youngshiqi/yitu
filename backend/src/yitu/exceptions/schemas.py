from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yitu.exceptions.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ResolutionCode,
)


class ExceptionCreate(BaseModel):
    """人工上报异常时允许调用方提交的最小字段。"""

    shipment_id: UUID
    case_type: ExceptionType
    description: str = Field(min_length=1, max_length=2000)
    evidence_summary: dict[str, object] = Field(default_factory=dict)


class ExceptionListFilters(BaseModel):
    """异常列表筛选条件。"""

    shipment_id: UUID | None = None
    status: ExceptionStatus | None = None
    case_type: ExceptionType | None = None
    severity: ExceptionSeverity | None = None
    responsible_station_id: UUID | None = None
    assigned_to: UUID | None = None
    blocks_fulfillment: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ExceptionAssign(BaseModel):
    """分配异常处理责任。"""

    assignee_id: UUID
    responsible_station_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class ExceptionAction(BaseModel):
    """异常状态动作请求。"""

    reason: str | None = Field(default=None, max_length=1000)


class ExceptionResolve(BaseModel):
    """解决异常请求。"""

    resolution_code: ResolutionCode
    reason: str = Field(min_length=1, max_length=1000)


class ExceptionTaskReassign(BaseModel):
    """异常处理中重新分配履约任务。"""

    old_task_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class ExceptionTaskReassignmentView(BaseModel):
    """任务重派结果视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    old_task_id: UUID
    new_task_id: UUID
    reason: str
    actor_id: UUID
    idempotency_key: str
    created_at: datetime


class ExceptionView(BaseModel):
    """异常工单公开详情视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shipment_id: UUID
    case_type: ExceptionType
    severity: ExceptionSeverity
    status: ExceptionStatus
    description: str
    evidence_summary: dict[str, object]
    blocks_fulfillment: bool
    frozen_shipment_status: str | None
    reported_by: UUID | None
    assigned_to: UUID | None
    responsible_station_id: UUID | None
    opened_at: datetime
    assigned_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None


class ExceptionListResponse(BaseModel):
    """异常列表分页响应。"""

    items: list[ExceptionView]
    total: int
    limit: int
    offset: int
