"""支付 HTTP 入口。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser, get_current_user
from yitu.payments.schemas import PaymentTransactionView, PayRequest, SupplementRequest
from yitu.payments.service import PaymentService
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])
_current_user = Depends(get_current_user)
_session = Depends(get_session)


@router.post("/quotes/{quote_id}/pay", response_model=PaymentTransactionView, status_code=status.HTTP_201_CREATED)
async def pay_quote(quote_id: UUID, request: PayRequest, idempotency_key: str = Header(alias="Idempotency-Key"), user: CurrentUser = _current_user, session: AsyncSession = _session) -> PaymentTransactionView:
    result = await PaymentService(session).pay_quote(quote_id, request, user, idempotency_key)
    await session.commit()
    return result


@router.post("/quotes/{quote_id}/supplement", response_model=PaymentTransactionView, status_code=status.HTTP_201_CREATED)
async def pay_supplement(quote_id: UUID, request: SupplementRequest, idempotency_key: str = Header(alias="Idempotency-Key"), user: CurrentUser = _current_user, session: AsyncSession = _session) -> PaymentTransactionView:
    result = await PaymentService(session).pay_supplement(quote_id, request, user, idempotency_key)
    await session.commit()
    return result


@router.post("/transactions/{transaction_id}/refund", response_model=PaymentTransactionView, status_code=status.HTTP_201_CREATED)
async def refund_payment(transaction_id: UUID, idempotency_key: str = Header(alias="Idempotency-Key"), user: CurrentUser = _current_user, session: AsyncSession = _session) -> PaymentTransactionView:
    result = await PaymentService(session).refund_payment(transaction_id, user, idempotency_key)
    await session.commit()
    return result
