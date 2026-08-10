"""任务六恢复动作的应用服务。"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.payments.models import PaymentTransaction
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.returns.enums import RecoveryAction, RecoveryStatus
from yitu.returns.models import RecoveryCase
from yitu.returns.schemas import RecoveryCommand, RecoveryShipmentView, RecoveryView
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.enums import DeliveryMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.transport_models import TransportLeg, TransportLegStatus
from yitu.sla.service import SLAService
from yitu.tracking.service import append_tracking_event


class ReturnService:
    """编排取消、拦截、重派、转自取和退回，不覆盖历史履约事实。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cancel(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.CANCEL,
            request,
            actor,
            idempotency_key,
            request_id,
            self._cancel_operation,
        )

    async def request_interception(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.INTERCEPTION,
            request,
            actor,
            idempotency_key,
            request_id,
            self._interception_operation,
        )

    async def redeliver(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.REDELIVERY,
            request,
            actor,
            idempotency_key,
            request_id,
            self._redelivery_operation,
        )

    async def convert_to_pickup(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.CONVERT_TO_PICKUP,
            request,
            actor,
            idempotency_key,
            request_id,
            self._convert_to_pickup_operation,
        )

    async def approve_return(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.RETURN,
            request,
            actor,
            idempotency_key,
            request_id,
            self._approve_return_operation,
        )

    async def advance_return(
        self,
        shipment_id: UUID,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryShipmentView:
        return await self._execute(
            shipment_id,
            RecoveryAction.RETURN,
            request,
            actor,
            idempotency_key,
            request_id,
            self._advance_return_operation,
        )

    async def _execute(
        self,
        shipment_id: UUID,
        action: RecoveryAction,
        request: RecoveryCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
        operation: "_RecoveryOperation",
    ) -> RecoveryShipmentView:
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))

        async def wrapped() -> IdempotencyResponse:
            shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment_id)
            self._assert_actor_scope(shipment, actor)
            recovery = await self._create_recovery_case(
                shipment,
                action,
                request.reason,
                actor,
                idempotency_key,
                request_id,
            )
            refund_amount, new_task_id = await operation(shipment, recovery, actor, request.reason, request_id, idempotency_key)
            await self._record_facts(shipment, recovery, actor, request.reason, request_id)
            view = RecoveryShipmentView(
                shipment_id=shipment.id,
                shipment_status=ShipmentStatus(shipment.status),
                recovery=RecoveryView.model_validate(recovery),
                refund_amount_cents=refund_amount,
                new_task_id=new_task_id,
            )
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"recovery:{action.value}:{shipment_id}:{actor.id}",
            idempotency_key,
            request_hash,
            wrapped,
        )
        return RecoveryShipmentView.model_validate(result.body)

    async def _cancel_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        actor: CurrentUser,
        reason: str,
        _request_id: str,
        idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) not in {
            ShipmentStatus.PENDING_PAYMENT,
            ShipmentStatus.PENDING_PICKUP,
            ShipmentStatus.WAITING_FOR_DROPOFF,
        }:
            raise AppError("SHIPMENT_NOT_CANCELLABLE", "当前运单不可取消", 409)
        refund_amount = await self._refund_paid_amount(shipment, actor, idempotency_key)
        shipment.status = ShipmentStatus.CANCELLED
        recovery.status = RecoveryStatus.COMPLETED
        recovery.completed_at = Clock.now()
        await self._cancel_active_tasks(shipment.id, reason)
        await SLAService(self._session).cancel_active_for_shipment(shipment.id, "cancel")
        return refund_amount, None

    async def _interception_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        _actor: CurrentUser,
        _reason: str,
        _request_id: str,
        _idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) not in {
            ShipmentStatus.PICKED_UP,
            ShipmentStatus.AT_ORIGIN_STATION,
            ShipmentStatus.IN_LINEHAUL,
            ShipmentStatus.AT_DESTINATION_STATION,
            ShipmentStatus.DELIVERY_ASSIGNED,
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP,
        }:
            raise AppError("INTERCEPTION_NOT_ALLOWED", "当前阶段不能发起拦截", 409)
        recovery.status = RecoveryStatus.REQUESTED
        return 0, None

    async def _redelivery_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        _actor: CurrentUser,
        reason: str,
        _request_id: str,
        _idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) not in {ShipmentStatus.DELIVERY_ASSIGNED, ShipmentStatus.OUT_FOR_DELIVERY}:
            raise AppError("REDELIVERY_NOT_ALLOWED", "当前阶段不能重新派送", 409)
        if shipment.destination_station_id is None:
            raise AppError("DESTINATION_STATION_REQUIRED", "运单缺少目标网点", 409)
        await self._cancel_active_delivery_tasks(shipment.id, reason)
        task = CourierTask(
            shipment_id=shipment.id,
            station_id=shipment.destination_station_id,
            task_type=CourierTaskType.DELIVERY,
            status=CourierTaskStatus.AVAILABLE,
        )
        self._session.add(task)
        await self._session.flush()
        await SLAService(self._session).start_recovery_stage(shipment.id, "DELIVERY_REDELIVERY")
        shipment.status = ShipmentStatus.DELIVERY_ASSIGNED
        recovery.status = RecoveryStatus.COMPLETED
        recovery.completed_at = Clock.now()
        return 0, task.id

    async def _convert_to_pickup_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        _actor: CurrentUser,
        reason: str,
        _request_id: str,
        _idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) not in {
            ShipmentStatus.AT_DESTINATION_STATION,
            ShipmentStatus.DELIVERY_ASSIGNED,
            ShipmentStatus.OUT_FOR_DELIVERY,
        }:
            raise AppError("CONVERT_TO_PICKUP_NOT_ALLOWED", "当前阶段不能转为网点自取", 409)
        await self._cancel_active_delivery_tasks(shipment.id, reason)
        shipment.delivery_method = DeliveryMethod.STATION_PICKUP
        shipment.status = ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP
        await SLAService(self._session).start_recovery_stage(shipment.id, "PICKUP_AT_STATION")
        recovery.status = RecoveryStatus.COMPLETED
        recovery.completed_at = Clock.now()
        return 0, None

    async def _approve_return_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        _actor: CurrentUser,
        _reason: str,
        _request_id: str,
        _idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) in {ShipmentStatus.PENDING_PAYMENT, ShipmentStatus.CANCELLED, ShipmentStatus.DELIVERED}:
            raise AppError("RETURN_NOT_ALLOWED", "当前阶段不能审批退回", 409)
        shipment.status = ShipmentStatus.RETURN_APPROVED
        await SLAService(self._session).start_recovery_stage(shipment.id, "RETURN")
        recovery.status = RecoveryStatus.APPROVED
        return 0, None

    async def _advance_return_operation(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        actor: CurrentUser,
        _reason: str,
        _request_id: str,
        idempotency_key: str,
    ) -> tuple[int, UUID | None]:
        if ShipmentStatus(shipment.status) is ShipmentStatus.RETURN_APPROVED:
            shipment.status = ShipmentStatus.IN_RETURN
            if shipment.destination_station_id is not None:
                self._session.add(
                    TransportLeg(
                        shipment_id=shipment.id,
                        origin_station_id=shipment.destination_station_id,
                        destination_station_id=shipment.origin_station_id,
                        status=TransportLegStatus.IN_TRANSIT,
                        started_at=Clock.now(),
                    )
                )
            recovery.status = RecoveryStatus.IN_PROGRESS
            return 0, None
        if ShipmentStatus(shipment.status) is ShipmentStatus.IN_RETURN:
            shipment.status = ShipmentStatus.RETURNED
            recovery.status = RecoveryStatus.COMPLETED
            recovery.completed_at = Clock.now()
            refund_amount = await self._refund_paid_amount(shipment, actor, idempotency_key)
            await SLAService(self._session).cancel_active_for_shipment(shipment.id, "return_completed")
            leg = await self._session.scalar(
                select(TransportLeg)
                .where(
                    TransportLeg.shipment_id == shipment.id,
                    TransportLeg.status == TransportLegStatus.IN_TRANSIT,
                )
                .order_by(TransportLeg.started_at.desc())
            )
            if leg is not None:
                leg.status = TransportLegStatus.ARRIVED
                leg.arrived_at = Clock.now()
            return refund_amount, None
        raise AppError("RETURN_NOT_ADVANCEABLE", "退回流程当前不可推进", 409)

    async def _create_recovery_case(
        self,
        shipment: Shipment,
        action: RecoveryAction,
        reason: str,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> RecoveryCase:
        recovery = RecoveryCase(
            shipment_id=shipment.id,
            action=action,
            status=RecoveryStatus.REQUESTED,
            reason=reason,
            actor_id=actor.id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            created_at=Clock.now(),
        )
        self._session.add(recovery)
        await self._session.flush()
        return recovery

    async def _refund_paid_amount(
        self,
        shipment: Shipment,
        actor: CurrentUser,
        idempotency_key: str,
    ) -> int:
        paid = await self._paid_total(shipment.id)
        refunded = await self._refund_total(shipment.id)
        amount = paid - refunded
        if amount <= 0:
            return 0
        payment = await self._session.scalar(
            select(PaymentTransaction)
            .where(
                PaymentTransaction.shipment_id == shipment.id,
                PaymentTransaction.transaction_type == "PAYMENT",
                PaymentTransaction.status == "SUCCEEDED",
            )
            .order_by(PaymentTransaction.created_at)
        )
        refund = PaymentTransaction(
            owner_id=shipment.owner_id,
            shipment_id=shipment.id,
            related_transaction_id=payment.id if payment is not None else None,
            transaction_type="REFUND",
            status="SUCCEEDED",
            amount_cents=amount,
            idempotency_key=f"recovery:{idempotency_key}:refund",
            request_hash=canonical_json_sha256({"shipment_id": str(shipment.id), "amount_cents": amount}),
            created_at=Clock.now(),
        )
        self._session.add(refund)
        await self._session.flush()
        return amount

    async def _paid_total(self, shipment_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(PaymentTransaction.amount_cents), 0)).where(
                PaymentTransaction.shipment_id == shipment_id,
                PaymentTransaction.transaction_type.in_(["PAYMENT", "SUPPLEMENT"]),
                PaymentTransaction.status == "SUCCEEDED",
            )
        )
        return int(total or 0)

    async def _refund_total(self, shipment_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(PaymentTransaction.amount_cents), 0)).where(
                PaymentTransaction.shipment_id == shipment_id,
                PaymentTransaction.transaction_type == "REFUND",
                PaymentTransaction.status == "SUCCEEDED",
            )
        )
        return int(total or 0)

    async def _cancel_active_tasks(self, shipment_id: UUID, reason: str) -> None:
        tasks = await self._session.scalars(
            select(CourierTask).where(
                CourierTask.shipment_id == shipment_id,
                CourierTask.status.in_([CourierTaskStatus.AVAILABLE, CourierTaskStatus.ACCEPTED]),
            )
        )
        now = Clock.now()
        for task in tasks:
            task.status = CourierTaskStatus.CANCELLED
            task.closed_reason = reason
            task.closed_at = now

    async def _cancel_active_delivery_tasks(self, shipment_id: UUID, reason: str) -> None:
        tasks = await self._session.scalars(
            select(CourierTask).where(
                CourierTask.shipment_id == shipment_id,
                CourierTask.task_type == CourierTaskType.DELIVERY,
                CourierTask.status.in_([CourierTaskStatus.AVAILABLE, CourierTaskStatus.ACCEPTED]),
            )
        )
        now = Clock.now()
        for task in tasks:
            task.status = CourierTaskStatus.CANCELLED
            task.closed_reason = reason
            task.closed_at = now

    async def _record_facts(
        self,
        shipment: Shipment,
        recovery: RecoveryCase,
        actor: CurrentUser,
        reason: str,
        request_id: str,
    ) -> None:
        await append_tracking_event(
            self._session,
            shipment.id,
            f"RECOVERY_{recovery.action.value}",
            f"恢复动作已记录：{recovery.action.value}",
            f"tracking:recovery:{recovery.id}",
        )
        await AuditService(self._session).record(
            actor=str(actor.id),
            action=f"recovery.{recovery.action.value.lower()}",
            resource=f"shipment:{shipment.id}",
            before_summary=None,
            after_summary={
                "recovery_status": RecoveryStatus(recovery.status).value,
                "shipment_status": ShipmentStatus(shipment.status).value,
            },
            reason=reason,
            request_id=request_id,
        )

    def _assert_actor_scope(self, shipment: Shipment, actor: CurrentUser) -> None:
        if actor.role is Role.OPERATIONS_ADMIN:
            return
        if actor.role is Role.CUSTOMER:
            require_resource_owner(shipment.owner_id, actor)
            return
        raise AppError("FORBIDDEN_RECOVERY_ACTION", "当前角色不能执行恢复动作", 403)


_RecoveryOperation = Callable[
    [Shipment, RecoveryCase, CurrentUser, str, str, str],
    Awaitable[tuple[int, UUID | None]],
]
