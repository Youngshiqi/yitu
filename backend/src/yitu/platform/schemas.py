from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from yitu.platform.clock import to_business_timezone


class TimezoneAwareResponse(BaseModel):
    """约束响应中的时间值必须携带时区，避免 API 输出歧义时间。"""

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def reject_naive_datetime(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("datetime must be timezone-aware")
        if isinstance(value, datetime):
            return to_business_timezone(value)
        return value


class ErrorResponse(TimezoneAwareResponse):
    """统一的 API 错误响应结构。"""

    code: str
    message: str
    request_id: str
    details: dict[str, object] | None = None
