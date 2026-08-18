"""当前生效运费规则的确定性查询工具。"""

from pydantic import BaseModel, ConfigDict

from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.pricing.service import PricingService

_ROUTE_LABELS = {"SAME_CITY": "同城", "BJ_SH": "北京↔上海", "CROSS_REGION": "跨区"}

_BILLING_POLICY = (
    "计费规则：首重 1 公斤（含）以内只收基础运费；续重每满 500 克加收一次续重费；"
    "体积重 = 长×宽×高 ÷ 6000（单位克），计费重量取实际重量与体积重量的较大者；"
    "上门取件加收 3 元，网点自提减收 1 元（当前仅开放上门取件与送货上门）。"
)


class PricingRuleSummary(BaseModel):
    """一条线路当前生效的费用金额（单位分）。"""

    model_config = ConfigDict(extra="forbid")

    route_code: str
    route_label: str
    base_fee_cents: int
    additional_fee_cents: int
    remote_surcharge_cents: int


class PricingRulesResult(BaseModel):
    """运费规则的结构化结果，供模型组织自然语言回答。"""

    model_config = ConfigDict(extra="forbid")

    rules: list[PricingRuleSummary]
    policy: str


class PricingRuleTool:
    """读取数据库当前生效的运费规则，返回确定性规则说明。"""

    async def execute(self, context: ToolContext) -> ToolResult[PricingRulesResult]:
        rules = await PricingService(context.session).list_active_rules()
        summaries = [
            PricingRuleSummary(
                route_code=rule.route_code,
                route_label=_ROUTE_LABELS.get(rule.route_code, rule.route_code),
                base_fee_cents=rule.base_fee_cents,
                additional_fee_cents=rule.additional_fee_cents,
                remote_surcharge_cents=rule.remote_surcharge_cents,
            )
            for rule in rules
        ]
        return ToolResult(
            tool="pricing_rule",
            found=bool(summaries),
            data=PricingRulesResult(rules=summaries, policy=_BILLING_POLICY),
            message=self._format_message(summaries),
        )

    @staticmethod
    def _format_message(rules: list[PricingRuleSummary]) -> str:
        if not rules:
            return "当前没有已生效的运费规则。"
        lines = [_BILLING_POLICY]
        for rule in rules:
            line = (
                f"{rule.route_label}（{rule.route_code}）：基础运费 "
                f"{rule.base_fee_cents / 100:.2f} 元，续重每 500 克 "
                f"{rule.additional_fee_cents / 100:.2f} 元"
            )
            if rule.remote_surcharge_cents:
                line += f"，偏远附加费 {rule.remote_surcharge_cents / 100:.2f} 元"
            lines.append(line)
        return "\n".join(lines)
