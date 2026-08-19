"""执行与数据库无关的确定性计价规则。"""
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from math import ceil


@dataclass(frozen=True, slots=True)
class PricingInput:
    """报价所需的地区、服务和包裹尺寸快照。"""

    origin_district_code: str
    destination_district_code: str
    pickup_method: str
    delivery_method: str
    actual_weight_grams: int
    length_cm: int
    width_cm: int
    height_cm: int


@dataclass(frozen=True, slots=True)
class PricingRuleData:
    """一个已发布价格规则的不可变投影。"""

    version: str
    route_code: str
    base_fee_cents: int
    additional_fee_cents: int
    remote_surcharge_cents: int = 0


@dataclass(frozen=True, slots=True)
class FeeItem:
    """报价中的一项费用。"""

    code: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class QuoteCalculation:
    """纯策略计算结果，供快照服务持久化。"""

    rule_version: str
    route_code: str
    volume_weight_grams: int
    billable_weight_grams: int
    items: tuple[FeeItem, ...]
    total_cents: int


DEFAULT_RULES = {
    "SAME_CITY": PricingRuleData("pricing-demo-v1", "SAME_CITY", 800, 150),
    "BJ_SH": PricingRuleData("pricing-demo-v1", "BJ_SH", 1500, 500),
    "CROSS_REGION": PricingRuleData("pricing-demo-v1", "CROSS_REGION", 1800, 700),
}


def route_code(origin: str, destination: str) -> str:
    """根据六位行政区划编码匹配演示线路。"""
    if len(origin) != 6 or len(destination) != 6 or not origin.isdigit() or not destination.isdigit():
        raise ValueError("地区编码必须是六位数字")
    if origin[:2] == destination[:2]:
        return "SAME_CITY"
    if {origin[:2], destination[:2]} == {"11", "31"}:
        return "BJ_SH"
    return "CROSS_REGION"


def calculate_quote(payload: PricingInput, rule: PricingRuleData | None = None) -> QuoteCalculation:
    """按固定单位和整数金额计算报价。"""
    _validate_input(payload)
    selected_route = route_code(payload.origin_district_code, payload.destination_district_code)
    selected_rule = rule or DEFAULT_RULES[selected_route]
    volume_weight = int((Decimal(payload.length_cm * payload.width_cm * payload.height_cm) / Decimal(6)).quantize(Decimal(1), rounding=ROUND_CEILING))
    billable_weight = max(payload.actual_weight_grams, volume_weight)
    billed_units = max(0, ceil((billable_weight - 1000) / 500))
    items = [FeeItem("BASE_FEE", selected_rule.base_fee_cents)]
    if billed_units:
        items.append(FeeItem("ADDITIONAL_WEIGHT", billed_units * selected_rule.additional_fee_cents))
    if payload.pickup_method == "DOOR_PICKUP":
        items.append(FeeItem("PICKUP_SERVICE", 300))
    if payload.delivery_method == "STATION_PICKUP":
        items.append(FeeItem("STATION_PICKUP_DISCOUNT", -100))
    if selected_rule.remote_surcharge_cents:
        items.append(FeeItem("REMOTE_SURCHARGE", selected_rule.remote_surcharge_cents))
    return QuoteCalculation(selected_rule.version, selected_route, volume_weight, billable_weight, tuple(items), max(0, sum(item.amount_cents for item in items)))


def _validate_input(payload: PricingInput) -> None:
    if payload.actual_weight_grams <= 0 or any(value <= 0 for value in (payload.length_cm, payload.width_cm, payload.height_cm)):
        raise ValueError("重量和尺寸必须大于零")
