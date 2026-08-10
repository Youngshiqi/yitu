from uuid import UUID

from sqlalchemy import Select, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus
from yitu.exceptions.enums import ExceptionSourceType, ExceptionStatus
from yitu.exceptions.models import ExceptionCase, ExceptionTaskReassignment
from yitu.exceptions.schemas import (
    ExceptionAssign,
    ExceptionCreate,
    ExceptionListFilters,
    ExceptionResolve,
    ExceptionTaskReassign,
    ExceptionTaskReassignmentView,
    ExceptionView,
)
from yitu.exceptions.state_machine import (
    default_policy,
    reportable_types,
    resolution_is_executable,
    transition,
)
from yitu.identity.models import Role, Station, User
from yitu.identity.service import CurrentUser
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import (
    IdempotencyResponse,
    IdempotencyService,
    canonical_json_sha256,
)
from yitu.platform.outbox import OutboxService
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.enums import ShipmentStatus
from yitu.shipments.hold_models import ShipmentHold
from yitu.shipments.models import Shipment
from yitu.shipments.schemas import ShipmentResumeCommand, ShipmentResumeView
from yitu.sla.models import SLAPause
from yitu.sla.service import SLAService
from yitu.tracking.service import append_tracking_event


class ExceptionService:
    """编排异常人工开单和按角色读取异常工单。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_case(
        self,
        request: ExceptionCreate,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> ExceptionView:
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))
        scope = f"exception:open:{actor.id}"

        async def operation() -> IdempotencyResponse:
            shipment = await ShipmentControlService(self._session).lock_shipment(request.shipment_id)
            await self._assert_manual_report_allowed(request, shipment, actor)
            policy = default_policy(request.case_type)
            case = ExceptionCase(
                shipment_id=shipment.id,
                case_type=request.case_type,
                severity=policy.severity,
                status=ExceptionStatus.OPEN,
                source_type=ExceptionSourceType.MANUAL,
                source_id=None,
                description=request.description,
                evidence_summary=request.evidence_summary,
                blocks_fulfillment=policy.blocks_fulfillment,
                frozen_shipment_status=shipment.status if policy.blocks_fulfillment else None,
                reported_by=actor.id,
                opened_at=Clock.now(),
                idempotency_key=idempotency_key,
                request_id=request_id,
            )
            self._session.add(case)
            await self._session.flush()
            if policy.blocks_fulfillment:
                await ShipmentControlService(self._session).place_exception_hold(
                    shipment_id=shipment.id,
                    source_type="EXCEPTION_CASE",
                    source_id=case.id,
                    reason=request.description,
                    actor=actor,
                    idempotency_key=f"hold:{case.id}:open",
                )
            await AuditService(self._session).record(
                actor=str(actor.id),
                action="exception.open",
                resource=f"exception:{case.id}",
                before_summary=None,
                after_summary={
                    "status": ExceptionStatus.OPEN.value,
                    "case_type": request.case_type.value,
                    "blocks_fulfillment": policy.blocks_fulfillment,
                },
                reason=request.description,
                request_id=request_id,
            )
            await OutboxService(self._session).append(
                event_type="notification.requested",
                business_id=f"exception:{case.id}",
                payload={
                    "recipient_id": str(shipment.owner_id),
                    "template_code": "EXCEPTION_OPENED",
                    "template_data": {"shipment_no": shipment.shipment_no},
                },
                idempotency_key=f"notification:exception:{case.id}:opened",
            )
            view = ExceptionView.model_validate(case)
            return IdempotencyResponse(201, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            scope,
            idempotency_key,
            request_hash,
            operation,
        )
        return ExceptionView.model_validate(result.body)

    async def get_case(self, case_id: UUID, actor: CurrentUser) -> ExceptionView:
        statement = self._scoped_cases(actor).where(ExceptionCase.id == case_id)
        case = await self._session.scalar(statement)
        if case is None:
            raise AppError("EXCEPTION_CASE_NOT_FOUND", "异常工单不存在", 404)
        return ExceptionView.model_validate(case)

    async def list_cases(
        self,
        actor: CurrentUser,
        filters: ExceptionListFilters | None = None,
    ) -> tuple[list[ExceptionView], int]:
        filters = filters or ExceptionListFilters()
        statement = self._apply_filters(self._scoped_cases(actor), filters)
        total = await self._session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = await self._session.scalars(
            statement.order_by(ExceptionCase.opened_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        return [ExceptionView.model_validate(case) for case in rows], int(total or 0)

    async def assign_case(
        self,
        case_id: UUID,
        request: ExceptionAssign,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> ExceptionView:
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))

        async def operation() -> IdempotencyResponse:
            self._require_operations_admin(actor)
            case = await self._lock_case(case_id)
            assignee = await self._session.get(User, request.assignee_id)
            station = await self._session.get(Station, request.responsible_station_id)
            if station is None:
                raise AppError("INVALID_RESPONSIBLE_STATION", "责任网点不存在", 422)
            if assignee is None or assignee.role not in {Role.STATION_OPERATOR, Role.OPERATIONS_ADMIN}:
                raise AppError("INVALID_CASE_ASSIGNEE", "处理人无效", 422)
            if assignee.role is Role.STATION_OPERATOR and assignee.station_id != station.id:
                raise AppError("INVALID_CASE_ASSIGNEE", "处理人不属于责任网点", 422)
            previous = ExceptionStatus(case.status)
            case.status = transition(previous, "assign")
            case.assigned_to = request.assignee_id
            case.responsible_station_id = request.responsible_station_id
            case.assigned_at = Clock.now()
            await self._record_audit(case, actor, "assign", previous, request.reason, request_id)
            await self._session.flush()
            view = ExceptionView.model_validate(case)
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"exception:assign:{case_id}:{actor.id}",
            idempotency_key,
            request_hash,
            operation,
        )
        return ExceptionView.model_validate(result.body)

    async def apply_action(
        self,
        case_id: UUID,
        action: str,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
        *,
        reason: str | None = None,
    ) -> ExceptionView:
        request_hash = canonical_json_sha256({"action": action, "reason": reason})

        async def operation() -> IdempotencyResponse:
            case = await self._lock_case(case_id)
            self._assert_can_manage(case, actor)
            previous = ExceptionStatus(case.status)
            if action == "close" and await self._case_has_active_hold(case.id):
                raise AppError("RESUME_PRECONDITION_FAILED", "阻断异常恢复履约前不能关闭", 409)
            case.status = transition(previous, action)
            now = Clock.now()
            if case.status is ExceptionStatus.CLOSED:
                case.closed_at = now
            await self._record_audit(case, actor, action, previous, reason, request_id)
            if action == "wait_for_customer":
                await self._append_owner_notification(case, "EXCEPTION_WAITING_FOR_CUSTOMER")
            await self._session.flush()
            view = ExceptionView.model_validate(case)
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"exception:{action}:{case_id}:{actor.id}",
            idempotency_key,
            request_hash,
            operation,
        )
        return ExceptionView.model_validate(result.body)

    async def resolve_case(
        self,
        case_id: UUID,
        request: ExceptionResolve,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> ExceptionView:
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))

        async def operation() -> IdempotencyResponse:
            case = await self._lock_case(case_id)
            self._assert_can_manage(case, actor)
            if not resolution_is_executable(request.resolution_code):
                raise AppError("RECOVERY_ACTION_NOT_IMPLEMENTED", "该恢复动作留待后续任务执行", 409)
            previous = ExceptionStatus(case.status)
            case.status = transition(previous, "resolve")
            case.resolution_code = request.resolution_code
            case.resolution_reason = request.reason
            case.resolved_at = Clock.now()
            await self._record_audit(case, actor, "resolve", previous, request.reason, request_id)
            await self._append_owner_notification(case, "EXCEPTION_RESOLVED")
            await self._session.flush()
            view = ExceptionView.model_validate(case)
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"exception:resolve:{case_id}:{actor.id}",
            idempotency_key,
            request_hash,
            operation,
        )
        return ExceptionView.model_validate(result.body)

    async def reassign_task(
        self,
        case_id: UUID,
        request: ExceptionTaskReassign,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> ExceptionTaskReassignmentView:
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))

        async def operation() -> IdempotencyResponse:
            self._require_operations_admin(actor)
            case = await self._lock_case(case_id)
            if ExceptionStatus(case.status) not in {ExceptionStatus.ASSIGNED, ExceptionStatus.PROCESSING}:
                raise AppError("TASK_NOT_REASSIGNABLE", "当前异常状态不允许重派任务", 409)
            old_task = await self._session.scalar(
                select(CourierTask)
                .where(CourierTask.id == request.old_task_id)
                .with_for_update()
            )
            if old_task is None or old_task.shipment_id != case.shipment_id:
                raise AppError("TASK_NOT_REASSIGNABLE", "任务不属于该异常运单", 409)
            if CourierTaskStatus(old_task.status) in {CourierTaskStatus.COMPLETED, CourierTaskStatus.CANCELLED}:
                raise AppError("TASK_NOT_REASSIGNABLE", "任务已完成或已关闭", 409)
            new_task = CourierTask(
                shipment_id=old_task.shipment_id,
                station_id=old_task.station_id,
                task_type=old_task.task_type,
                status=CourierTaskStatus.AVAILABLE,
                assignee_id=None,
            )
            self._session.add(new_task)
            await self._session.flush()
            old_task.status = CourierTaskStatus.CANCELLED
            old_task.closed_reason = request.reason
            old_task.closed_at = Clock.now()
            old_task.replaced_by_task_id = new_task.id
            fact = ExceptionTaskReassignment(
                case_id=case.id,
                old_task_id=old_task.id,
                new_task_id=new_task.id,
                reason=request.reason,
                actor_id=actor.id,
                idempotency_key=idempotency_key,
                created_at=Clock.now(),
            )
            self._session.add(fact)
            await self._record_audit(
                case,
                actor,
                "reassign_task",
                ExceptionStatus(case.status),
                request.reason,
                request_id,
            )
            await self._session.flush()
            view = ExceptionTaskReassignmentView.model_validate(fact)
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"exception:reassign-task:{case_id}:{request.old_task_id}:{actor.id}",
            idempotency_key,
            request_hash,
            operation,
        )
        return ExceptionTaskReassignmentView.model_validate(result.body)

    async def resume_shipment(
        self,
        shipment_id: UUID,
        request: ShipmentResumeCommand,
        actor: CurrentUser,
        idempotency_key: str,
        request_id: str,
    ) -> ShipmentResumeView:
        """显式释放异常 Hold，并只恢复对应异常来源的 SLA 暂停。"""
        request_hash = canonical_json_sha256(request.model_dump(mode="json"))

        async def operation() -> IdempotencyResponse:
            self._require_operations_admin(actor)
            shipment = await ShipmentControlService(self._session).lock_shipment(shipment_id)
            holds = await self._active_holds_for_update(shipment_id)
            if not holds:
                raise AppError("SHIPMENT_NOT_BLOCKED", "运单没有活动履约冻结", 409)
            frozen_statuses = {ShipmentStatus(hold.frozen_status) for hold in holds}
            if len(frozen_statuses) != 1:
                raise AppError("RESUME_PRECONDITION_FAILED", "活动冻结的原始履约阶段不一致", 409)
            frozen_status = next(iter(frozen_statuses))
            if request.target_status is not frozen_status:
                raise AppError("RESUME_TARGET_MISMATCH", "恢复目标阶段与冻结阶段不匹配", 409)
            source_ids = [hold.source_id for hold in holds if hold.source_type == "EXCEPTION_CASE"]
            if len(source_ids) != len(holds):
                raise AppError("RESUME_PRECONDITION_FAILED", "存在不支持的履约冻结来源", 409)
            cases = await self._blocking_cases_for_update(source_ids)
            if len(cases) != len(source_ids) or any(not case.blocks_fulfillment for case in cases):
                raise AppError("RESUME_PRECONDITION_FAILED", "履约冻结缺少对应阻断异常", 409)
            if any(ExceptionStatus(case.status) is not ExceptionStatus.RESOLVED for case in cases):
                raise AppError("UNRESOLVED_BLOCKING_CASES", "仍有阻断异常未解决", 409)
            await ShipmentControlService(self._session).assert_resume_preconditions(
                shipment,
                frozen_status,
            )
            active_pauses = await self._active_sla_pauses_for_sources(source_ids)
            sla_service = SLAService(self._session)
            for pause in active_pauses:
                if pause.source_id is None:
                    continue
                await sla_service.resume_for_source(
                    pause.instance_id,
                    source_type="EXCEPTION_CASE",
                    source_id=pause.source_id,
                    idempotency_key=f"sla:resume:{pause.source_id}:{idempotency_key}",
                )
            released = await ShipmentControlService(self._session).release_exception_holds(
                shipment_id=shipment_id,
                source_type="EXCEPTION_CASE",
                source_ids=source_ids,
                actor=actor,
                idempotency_key=idempotency_key,
            )
            for case in cases:
                case.blocks_fulfillment = False
            await append_tracking_event(
                self._session,
                shipment_id,
                "SHIPMENT_RESUMED",
                "履约已恢复",
                f"tracking:shipment:{shipment_id}:resumed:{idempotency_key}",
            )
            await AuditService(self._session).record(
                actor=str(actor.id),
                action="shipment.resume",
                resource=f"shipment:{shipment_id}",
                before_summary={"status": frozen_status.value, "active_hold_count": len(holds)},
                after_summary={"status": ShipmentStatus(shipment.status).value, "released_hold_count": len(released)},
                reason=request.reason,
                request_id=request_id,
            )
            await OutboxService(self._session).append(
                event_type="notification.requested",
                business_id=f"shipment:{shipment_id}:resumed",
                payload={
                    "recipient_id": str(shipment.owner_id),
                    "template_code": "SHIPMENT_RESUMED",
                    "template_data": {"shipment_no": shipment.shipment_no},
                },
                idempotency_key=f"notification:shipment:{shipment_id}:resumed:{idempotency_key}",
            )
            await self._session.flush()
            view = ShipmentResumeView(
                shipment_id=shipment.id,
                status=ShipmentStatus(shipment.status),
                resumed_hold_count=len(released),
            )
            return IdempotencyResponse(200, view.model_dump(mode="json"))

        result = await IdempotencyService(self._session).execute(
            f"shipment:resume:{shipment_id}:{actor.id}",
            idempotency_key,
            request_hash,
            operation,
        )
        return ShipmentResumeView.model_validate(result.body)

    async def _assert_manual_report_allowed(
        self,
        request: ExceptionCreate,
        shipment: Shipment,
        actor: CurrentUser,
    ) -> None:
        if request.case_type not in reportable_types(actor.role):
            raise AppError("EXCEPTION_TYPE_NOT_ALLOWED", "当前角色不能上报该异常类型", 403)
        if actor.role is Role.CUSTOMER:
            if shipment.owner_id != actor.id:
                raise AppError("FORBIDDEN_EXCEPTION_SCOPE", "不能访问该运单异常", 403)
            return
        if actor.role is Role.COURIER:
            allowed = await self._session.scalar(
                select(
                    exists().where(
                        CourierTask.shipment_id == shipment.id,
                        CourierTask.assignee_id == actor.id,
                        CourierTask.status == CourierTaskStatus.ACCEPTED,
                    )
                )
            )
            if allowed:
                return
        if actor.role is Role.STATION_OPERATOR and actor.station_id is not None:
            if shipment.origin_station_id == actor.station_id or shipment.destination_station_id == actor.station_id:
                return
            has_station_task = await self._session.scalar(
                select(
                    exists().where(
                        CourierTask.shipment_id == shipment.id,
                        CourierTask.station_id == actor.station_id,
                    )
                )
            )
            if has_station_task:
                return
        if actor.role is Role.OPERATIONS_ADMIN:
            return
        raise AppError("FORBIDDEN_EXCEPTION_SCOPE", "不能访问该运单异常", 403)

    async def _lock_case(self, case_id: UUID) -> ExceptionCase:
        case = await self._session.scalar(
            select(ExceptionCase).where(ExceptionCase.id == case_id).with_for_update()
        )
        if case is None:
            raise AppError("EXCEPTION_CASE_NOT_FOUND", "异常工单不存在", 404)
        await ShipmentControlService(self._session).lock_shipment(case.shipment_id)
        return case

    async def _active_holds_for_update(self, shipment_id: UUID) -> list[ShipmentHold]:
        return list(
            await self._session.scalars(
                select(ShipmentHold)
                .where(
                    ShipmentHold.shipment_id == shipment_id,
                    ShipmentHold.active.is_(True),
                )
                .with_for_update()
            )
        )

    async def _blocking_cases_for_update(self, case_ids: list[UUID]) -> list[ExceptionCase]:
        return list(
            await self._session.scalars(
                select(ExceptionCase)
                .where(ExceptionCase.id.in_(case_ids))
                .with_for_update()
            )
        )

    async def _active_sla_pauses_for_sources(self, source_ids: list[UUID]) -> list[SLAPause]:
        return list(
            await self._session.scalars(
                select(SLAPause).where(
                    SLAPause.source_type == "EXCEPTION_CASE",
                    SLAPause.source_id.in_(source_ids),
                    SLAPause.ended_at.is_(None),
                )
            )
        )

    async def _case_has_active_hold(self, case_id: UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        ShipmentHold.source_type == "EXCEPTION_CASE",
                        ShipmentHold.source_id == case_id,
                        ShipmentHold.active.is_(True),
                    )
                )
            )
        )

    @staticmethod
    def _require_operations_admin(actor: CurrentUser) -> None:
        if actor.role is not Role.OPERATIONS_ADMIN:
            raise AppError("FORBIDDEN_EXCEPTION_ACTION", "当前角色不能执行该异常动作", 403)

    def _assert_can_manage(self, case: ExceptionCase, actor: CurrentUser) -> None:
        if actor.role is Role.OPERATIONS_ADMIN:
            return
        if (
            actor.role is Role.STATION_OPERATOR
            and case.responsible_station_id == actor.station_id
            and (case.assigned_to is None or case.assigned_to == actor.id)
        ):
            return
        raise AppError("FORBIDDEN_EXCEPTION_ACTION", "当前角色不能执行该异常动作", 403)

    async def _record_audit(
        self,
        case: ExceptionCase,
        actor: CurrentUser,
        action: str,
        previous: ExceptionStatus,
        reason: str | None,
        request_id: str,
    ) -> None:
        await AuditService(self._session).record(
            actor=str(actor.id),
            action=f"exception.{action}",
            resource=f"exception:{case.id}",
            before_summary={"status": previous.value},
            after_summary={"status": ExceptionStatus(case.status).value},
            reason=reason,
            request_id=request_id,
        )

    async def _append_owner_notification(self, case: ExceptionCase, template_code: str) -> None:
        shipment = await self._session.get(Shipment, case.shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        await OutboxService(self._session).append(
            event_type="notification.requested",
            business_id=f"exception:{case.id}:{template_code.lower()}",
            payload={
                "recipient_id": str(shipment.owner_id),
                "template_code": template_code,
                "template_data": {"shipment_no": shipment.shipment_no},
            },
            idempotency_key=f"notification:exception:{case.id}:{template_code.lower()}",
        )

    def _scoped_cases(self, actor: CurrentUser) -> Select[tuple[ExceptionCase]]:
        statement = select(ExceptionCase).join(Shipment, Shipment.id == ExceptionCase.shipment_id)
        if actor.role is Role.OPERATIONS_ADMIN or actor.role is Role.SYSTEM_ADMIN:
            return statement
        if actor.role is Role.CUSTOMER:
            return statement.where(Shipment.owner_id == actor.id)
        if actor.role is Role.COURIER:
            return statement.where(
                or_(
                    ExceptionCase.reported_by == actor.id,
                    exists().where(
                        CourierTask.shipment_id == ExceptionCase.shipment_id,
                        CourierTask.assignee_id == actor.id,
                    ),
                )
            )
        if actor.role is Role.STATION_OPERATOR and actor.station_id is not None:
            return statement.where(
                or_(
                    Shipment.origin_station_id == actor.station_id,
                    Shipment.destination_station_id == actor.station_id,
                    exists().where(
                        CourierTask.shipment_id == ExceptionCase.shipment_id,
                        CourierTask.station_id == actor.station_id,
                    ),
                )
            )
        return statement.where(false())

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[ExceptionCase]],
        filters: ExceptionListFilters,
    ) -> Select[tuple[ExceptionCase]]:
        if filters.shipment_id is not None:
            statement = statement.where(ExceptionCase.shipment_id == filters.shipment_id)
        if filters.status is not None:
            statement = statement.where(ExceptionCase.status == filters.status)
        if filters.case_type is not None:
            statement = statement.where(ExceptionCase.case_type == filters.case_type)
        if filters.severity is not None:
            statement = statement.where(ExceptionCase.severity == filters.severity)
        if filters.responsible_station_id is not None:
            statement = statement.where(ExceptionCase.responsible_station_id == filters.responsible_station_id)
        if filters.assigned_to is not None:
            statement = statement.where(ExceptionCase.assigned_to == filters.assigned_to)
        if filters.blocks_fulfillment is not None:
            statement = statement.where(ExceptionCase.blocks_fulfillment.is_(filters.blocks_fulfillment))
        return statement
