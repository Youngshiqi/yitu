"""SLA 规则选择与截止时间计算。"""

from datetime import datetime, timedelta

from yitu.sla.calendar import add_work_hours
from yitu.sla.models import SLARule


def calculate_promised_at(rule: SLARule, started_at: datetime) -> datetime:
    """按照规则计算冻结的承诺时间。"""
    if rule.target_work_hours is not None:
        return add_work_hours(started_at, rule.target_work_hours)
    if rule.target_natural_hours is not None:
        return started_at + timedelta(hours=rule.target_natural_hours)
    raise ValueError("SLA 规则必须配置工作小时或自然小时")


def rule_is_effective(rule: SLARule, at: datetime) -> bool:
    """判断规则在指定时刻是否生效。"""
    if at < rule.effective_from:
        return False
    return rule.effective_to is None or at < rule.effective_to
