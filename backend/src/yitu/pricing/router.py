"""报价 HTTP 入口。"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser, get_current_user, require_resource_owner
from yitu.platform.database import get_session
from yitu.platform.errors import AppError
from yitu.pricing.models import QuoteSnapshot
from yitu.pricing.schemas import QuoteRequest, QuoteView, ReweighRequest
from yitu.pricing.service import PricingService

router = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])
_current_user = Depends(get_current_user)
_session = Depends(get_session)


@router.post("/quotes", response_model=QuoteView, status_code=status.HTTP_201_CREATED)
async def create_quote(request: QuoteRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: CurrentUser = _current_user, session: AsyncSession = _session) -> QuoteView:
    """创建客户报价快照；幂等键由后续支付流程继续关联。"""
    # 兼容旧版客户端：未携带幂等键时由服务端生成一次性键，避免请求在参数校验阶段返回 422。
    result = await PricingService(session).quote(request, user, idempotency_key or str(uuid4()))
    await session.commit()
    return result


@router.get("/quotes/{quote_id}", response_model=QuoteView)
async def get_quote(quote_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> QuoteView:
    snapshot = await session.get(QuoteSnapshot, quote_id)
    if snapshot is None:
        raise AppError("QUOTE_NOT_FOUND", "报价不存在", 404)
    require_resource_owner(snapshot.owner_id, user)
    return QuoteView.model_validate(snapshot)


@router.post("/quotes/{quote_id}/reweigh", response_model=QuoteView, status_code=status.HTTP_201_CREATED)
async def reweigh_quote(quote_id: UUID, request: ReweighRequest, user: CurrentUser = _current_user, session: AsyncSession = _session) -> QuoteView:
    result = await PricingService(session).reweigh(quote_id, request, user)
    await session.commit()
    return QuoteView.model_validate(result)
