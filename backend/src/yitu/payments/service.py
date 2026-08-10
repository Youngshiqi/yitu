"""模拟支付、补差价和取消退款应用服务。"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.payments.models import PaymentTransaction
from yitu.payments.schemas import PaymentTransactionView, PayRequest, SupplementRequest
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.platform.outbox import OutboxService
from yitu.pricing.models import QuoteSnapshot
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.enums import PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.service import ShipmentTransitionService


class PaymentService:
    """在运单事务内追加支付事实并推进允许的履约状态。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pay_quote(self, quote_id: UUID, request: PayRequest, actor: CurrentUser, idempotency_key: str) -> PaymentTransactionView:
        self._require_customer(actor)
        quote, shipment = await self._quote_and_shipment(quote_id, request.shipment_id, actor)
        if request.amount_cents != quote.total_cents:
            raise AppError("PAYMENT_AMOUNT_MISMATCH", "支付金额必须与报价一致", 409)

        async def operation() -> IdempotencyResponse:
            locked_shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment.id)
            if ShipmentStatus(locked_shipment.status) is not ShipmentStatus.PENDING_PAYMENT:
                raise AppError("SHIPMENT_NOT_PAYABLE", "运单当前状态不可支付", 409)
            transaction = PaymentTransaction(owner_id=actor.id, quote_id=quote.id, shipment_id=locked_shipment.id, transaction_type="PAYMENT", status="SUCCEEDED", amount_cents=request.amount_cents, idempotency_key=idempotency_key, request_hash=canonical_json_sha256(request.model_dump(mode="json")), created_at=Clock.now())
            self._session.add(transaction)
            target = ShipmentStatus.PENDING_PICKUP if PickupMethod(locked_shipment.pickup_method) is PickupMethod.DOOR_PICKUP else ShipmentStatus.WAITING_FOR_DROPOFF
            await ShipmentTransitionService(self._session).transition(locked_shipment, target, actor, "confirm_payment", f"payment:{locked_shipment.id}")
            await OutboxService(self._session).append(
                event_type="notification.requested",
                business_id=f"shipment:{locked_shipment.id}",
                payload={
                    "recipient_id": str(actor.id),
                    "template_code": "PAYMENT_SUCCESS",
                    "template_data": {"shipment_no": locked_shipment.shipment_no},
                },
                idempotency_key=f"notification:{locked_shipment.id}:payment-success",
            )
            await self._session.flush()
            return IdempotencyResponse(201, PaymentTransactionView.model_validate(transaction).model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(f"payment:pay:{actor.id}", idempotency_key, canonical_json_sha256(request.model_dump(mode="json")), operation)
        return PaymentTransactionView.model_validate(result.body)

    async def pay_supplement(self, quote_id: UUID, request: SupplementRequest, actor: CurrentUser, idempotency_key: str) -> PaymentTransactionView:
        self._require_customer(actor)
        quote, shipment = await self._quote_and_shipment(quote_id, request.shipment_id, actor)
        paid_total = await self._paid_total(shipment.id)
        required = quote.total_cents - paid_total
        if required <= 0 or request.amount_cents != required:
            raise AppError("SUPPLEMENT_AMOUNT_MISMATCH", "补差价必须等于复重后的应付差额", 409)

        async def operation() -> IdempotencyResponse:
            transaction = PaymentTransaction(owner_id=actor.id, quote_id=quote.id, shipment_id=shipment.id, transaction_type="SUPPLEMENT", status="SUCCEEDED", amount_cents=request.amount_cents, idempotency_key=idempotency_key, request_hash=canonical_json_sha256(request.model_dump(mode="json")), created_at=Clock.now())
            self._session.add(transaction)
            await self._session.flush()
            return IdempotencyResponse(201, PaymentTransactionView.model_validate(transaction).model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(f"payment:supplement:{actor.id}", idempotency_key, canonical_json_sha256(request.model_dump(mode="json")), operation)
        return PaymentTransactionView.model_validate(result.body)

    async def refund_payment(self, transaction_id: UUID, actor: CurrentUser, idempotency_key: str) -> PaymentTransactionView:
        self._require_customer(actor)
        payment = await self._session.get(PaymentTransaction, transaction_id)
        if payment is None or payment.transaction_type != "PAYMENT":
            raise AppError("PAYMENT_NOT_FOUND", "原支付流水不存在", 404)
        require_resource_owner(payment.owner_id, actor)
        shipment = await self._session.get(Shipment, payment.shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        if ShipmentStatus(shipment.status) not in {ShipmentStatus.PENDING_PICKUP, ShipmentStatus.WAITING_FOR_DROPOFF}:
            raise AppError("SHIPMENT_NOT_REFUNDABLE", "运单已揽收，不能直接取消退款", 409)
        refund_total = await self._paid_total(shipment.id)

        async def operation() -> IdempotencyResponse:
            refund = PaymentTransaction(owner_id=actor.id, shipment_id=shipment.id, related_transaction_id=payment.id, transaction_type="REFUND", status="SUCCEEDED", amount_cents=refund_total, idempotency_key=idempotency_key, request_hash=canonical_json_sha256({"transaction_id": str(transaction_id)}), created_at=Clock.now())
            self._session.add(refund)
            await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.CANCELLED, actor, "cancel", f"refund:{transaction_id}")
            await self._session.flush()
            return IdempotencyResponse(201, PaymentTransactionView.model_validate(refund).model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(f"payment:refund:{actor.id}", idempotency_key, canonical_json_sha256({"transaction_id": str(transaction_id)}), operation)
        return PaymentTransactionView.model_validate(result.body)

    async def _quote_and_shipment(self, quote_id: UUID, shipment_id: UUID, actor: CurrentUser) -> tuple[QuoteSnapshot, Shipment]:
        quote = await self._session.get(QuoteSnapshot, quote_id)
        if quote is None:
            raise AppError("QUOTE_NOT_FOUND", "报价不存在", 404)
        require_resource_owner(quote.owner_id, actor)
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        require_resource_owner(shipment.owner_id, actor)
        if quote.owner_id != shipment.owner_id:
            raise AppError("FORBIDDEN_RESOURCE_OWNER", "报价和运单不属于同一客户", 403)
        return quote, shipment

    async def _paid_total(self, shipment_id: UUID) -> int:
        total = await self._session.scalar(select(func.coalesce(func.sum(PaymentTransaction.amount_cents), 0)).where(PaymentTransaction.shipment_id == shipment_id, PaymentTransaction.transaction_type.in_(["PAYMENT", "SUPPLEMENT"]), PaymentTransaction.status == "SUCCEEDED"))
        return int(total or 0)

    @staticmethod
    def _require_customer(actor: CurrentUser) -> None:
        if actor.role is not Role.CUSTOMER:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
