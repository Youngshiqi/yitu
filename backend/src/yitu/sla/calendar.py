"""SLA 工作时间日历。

演示基线按中国大陆时间计算，周一至周六 09:00-18:00 为工作时间，
周日不计工作小时。法定节假日暂由后续运营配置扩展。
"""

from datetime import datetime, timedelta

from yitu.platform.clock import to_business_timezone

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 18
WORKDAY_MINUTES = (BUSINESS_END_HOUR - BUSINESS_START_HOUR) * 60


def _is_workday(value: datetime) -> bool:
    return value.weekday() != 6


def _at_business_start(value: datetime) -> datetime:
    return value.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)


def _next_business_start(value: datetime) -> datetime:
    candidate = value
    while True:
        if _is_workday(candidate):
            start = _at_business_start(candidate)
            if candidate <= start:
                return start
            if candidate < start + timedelta(hours=9):
                return candidate
        candidate = _at_business_start(candidate + timedelta(days=1))


def _period_end(value: datetime) -> datetime:
    return _at_business_start(value) + timedelta(hours=9)


def add_work_hours(start: datetime, hours: float) -> datetime:
    """从起点增加工作小时，结果仍带业务时区。"""
    if hours < 0:
        raise ValueError("hours must be non-negative")
    current = to_business_timezone(start)
    remaining = timedelta(hours=hours)
    while remaining:
        current = _next_business_start(current)
        available = _period_end(current) - current
        if remaining <= available:
            return current + remaining
        remaining -= available
        current = _at_business_start(current + timedelta(days=1))
    return current


def work_hours_between(start: datetime, end: datetime) -> timedelta:
    """计算两个时刻之间落在工作日营业时间内的时长。"""
    start_local = to_business_timezone(start)
    end_local = to_business_timezone(end)
    if end_local <= start_local:
        return timedelta(0)
    total = timedelta(0)
    current = start_local
    while current < end_local:
        if _is_workday(current):
            window_start = max(current, _at_business_start(current))
            window_end = min(end_local, _period_end(current))
            if window_end > window_start:
                total += window_end - window_start
        current = _at_business_start(current + timedelta(days=1))
    return total
