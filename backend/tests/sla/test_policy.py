from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from yitu.sla.models import SLARule
from yitu.sla.policy import calculate_promised_at

TZ = ZoneInfo("Asia/Shanghai")


def test_work_hour_rule_freezes_promised_time() -> None:
    rule = SLARule(
        id=uuid4(), version="v1", route_code="BJ-SH", service_type="STANDARD", stage="DELIVERY",
        target_work_hours=2, effective_from=datetime(2026, 1, 1, tzinfo=TZ),
    )
    assert calculate_promised_at(rule, datetime(2026, 8, 14, 17, tzinfo=TZ)) == datetime(2026, 8, 15, 10, tzinfo=TZ)


def test_natural_hour_rule_uses_elapsed_time() -> None:
    rule = SLARule(
        id=uuid4(), version="v1", route_code="LOCAL", service_type="STANDARD", stage="LINEHAUL",
        target_natural_hours=24, effective_from=datetime(2026, 1, 1, tzinfo=TZ),
    )
    start = datetime(2026, 8, 14, 17, tzinfo=TZ)
    assert calculate_promised_at(rule, start) == datetime(2026, 8, 15, 17, tzinfo=TZ)
