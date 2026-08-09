from datetime import datetime
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


class Clock:
    """为业务代码提供统一且带时区的当前时间。"""

    @staticmethod
    def now() -> datetime:
        return datetime.now(BUSINESS_TIMEZONE)


def to_business_timezone(value: datetime) -> datetime:
    """将带时区时间转换为业务时区，拒绝会产生歧义的无时区时间。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(BUSINESS_TIMEZONE)
