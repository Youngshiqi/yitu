from datetime import UTC, datetime, timedelta

import pytest

from yitu.platform.clock import Clock, to_business_timezone


def test_converts_utc_datetime_to_business_timezone() -> None:
    converted = to_business_timezone(datetime(2026, 8, 9, 0, 0, tzinfo=UTC))

    assert converted.isoformat() == "2026-08-09T08:00:00+08:00"


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_business_timezone(datetime.fromisoformat("2026-08-09T00:00:00"))


def test_clock_now_uses_business_timezone() -> None:
    assert Clock().now().utcoffset() == timedelta(hours=8)
