from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from yitu.sla.calendar import add_work_hours, work_hours_between

TZ = ZoneInfo("Asia/Shanghai")


def test_work_hours_skip_sunday_and_outside_business_hours() -> None:
    friday = datetime(2026, 8, 14, 17, 0, tzinfo=TZ)
    deadline = add_work_hours(friday, 2)
    assert deadline == datetime(2026, 8, 15, 10, 0, tzinfo=TZ)
    assert work_hours_between(friday, deadline) == timedelta(hours=2)


def test_work_hours_skip_sunday_when_crossing_weekend() -> None:
    saturday = datetime(2026, 8, 15, 17, 0, tzinfo=TZ)
    assert add_work_hours(saturday, 2) == datetime(2026, 8, 17, 10, 0, tzinfo=TZ)


def test_naive_datetime_is_rejected() -> None:
    try:
        add_work_hours(datetime(2026, 8, 14, 9, 0), 1)  # noqa: DTZ001
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("必须拒绝无时区时间")
