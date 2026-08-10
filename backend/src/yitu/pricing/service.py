"""报价快照应用服务。"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.pricing.models import PricingRule, QuoteSnapshot
from yitu.pricing.policy import (
    PricingInput,
    PricingRuleData,
    calculate_quote,
    route_code,
)
from yitu.pricing.schemas import QuoteRequest, QuoteView, ReweighRequest


class PricingService:
    """创建不可变报价并从历史快照派生复重报价。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def quote(self, request: QuoteRequest, actor: CurrentUser, idempotency_key: str) -> QuoteView:
        if actor.role is not Role.CUSTOMER:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        async def operation() -> IdempotencyResponse:
            rule = await self._active_rule(request.origin_district_code, request.destination_district_code)
            calculation = calculate_quote(_to_input(request), _rule_data(rule))
            snapshot = QuoteSnapshot(owner_id=actor.id, rule_id=rule.id, rule_version=rule.version, input_snapshot=request.model_dump(mode="json"), fee_items=[{"code": item.code, "amount_cents": item.amount_cents} for item in calculation.items], volume_weight_grams=calculation.volume_weight_grams, billable_weight_grams=calculation.billable_weight_grams, total_cents=calculation.total_cents, created_at=Clock.now())
            self._session.add(snapshot)
            await self._session.flush()
            return IdempotencyResponse(201, QuoteView.model_validate(snapshot).model_dump(mode="json"))

        response = await IdempotencyService(self._session).execute(f"pricing:quote:{actor.id}", idempotency_key, canonical_json_sha256(request.model_dump(mode="json")), operation)
        return QuoteView.model_validate(response.body)

    async def reweigh(self, quote_id: UUID, request: ReweighRequest, actor: CurrentUser) -> QuoteSnapshot:
        existing = await self._session.get(QuoteSnapshot, quote_id)
        if existing is None:
            raise AppError("QUOTE_NOT_FOUND", "报价不存在", 404)
        require_resource_owner(existing.owner_id, actor)
        original = QuoteRequest.model_validate(existing.input_snapshot).model_copy(update=request.model_dump())
        rule = await self._session.get(PricingRule, existing.rule_id)
        if rule is None:
            raise AppError("PRICING_RULE_NOT_FOUND", "报价规则不存在", 409)
        calculation = calculate_quote(_to_input(original), _rule_data(rule))
        snapshot = QuoteSnapshot(owner_id=existing.owner_id, rule_id=rule.id, source_quote_id=existing.id, rule_version=rule.version, input_snapshot=original.model_dump(mode="json"), fee_items=[{"code": item.code, "amount_cents": item.amount_cents} for item in calculation.items], volume_weight_grams=calculation.volume_weight_grams, billable_weight_grams=calculation.billable_weight_grams, total_cents=calculation.total_cents, created_at=Clock.now())
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def _active_rule(self, origin: str, destination: str) -> PricingRule:
        code = route_code(origin, destination)
        rule = await self._session.scalar(select(PricingRule).where(PricingRule.route_code == code, PricingRule.effective_to.is_(None)).order_by(PricingRule.effective_from.desc()))
        if rule is None:
            raise AppError("ROUTE_NOT_SUPPORTED", "当前线路暂不支持报价", 422)
        return rule


def _rule_data(rule: PricingRule) -> PricingRuleData:
    return PricingRuleData(rule.version, rule.route_code, rule.base_fee_cents, rule.additional_fee_cents, rule.remote_surcharge_cents)


def _to_input(request: QuoteRequest) -> PricingInput:
    return PricingInput(**request.model_dump())
