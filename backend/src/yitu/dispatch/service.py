from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_station_scope
from yitu.platform.errors import AppError
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.enums import PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.service import ShipmentTransitionService


class DispatchService:
    """处理始发端揽收、自寄验收和网点交接动作。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pickup_task(self, shipment: Shipment, station_id: UUID) -> CourierTask:
        """为上门揽收运单创建一个待接的揽收任务。"""
        if PickupMethod(shipment.pickup_method) is not PickupMethod.DOOR_PICKUP:
            raise AppError("PICKUP_TASK_NOT_REQUIRED", "网点自寄不创建揽收任务", 409)
        task = CourierTask(shipment_id=shipment.id, station_id=station_id, task_type=CourierTaskType.PICKUP, status=CourierTaskStatus.AVAILABLE)
        self._session.add(task)
        await self._session.flush()
        return task

    async def accept_task(self, task_id: UUID, actor: CurrentUser, request_id: str) -> CourierTask:
        """由所属网点快递员接下待处理揽收任务。"""
        if actor.role is not Role.COURIER:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        task = await self._get_task(task_id)
        require_station_scope(task.station_id, actor)
        await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(task.shipment_id)
        accepted = await self._session.scalar(
            update(CourierTask)
            .where(
                CourierTask.id == task_id,
                CourierTask.status == CourierTaskStatus.AVAILABLE,
            )
            .values(status=CourierTaskStatus.ACCEPTED, assignee_id=actor.id)
            .returning(CourierTask)
        )
        if accepted is None:
            raise AppError("TASK_ALREADY_ASSIGNED", "任务已被其他快递员接单", 409)
        shipment = await self._get_shipment(accepted.shipment_id)
        task_type = CourierTaskType(accepted.task_type)
        target = (
            ShipmentStatus.PICKUP_ASSIGNED
            if task_type is CourierTaskType.PICKUP
            else ShipmentStatus.DELIVERY_ASSIGNED
        )
        action = "assign_pickup" if task_type is CourierTaskType.PICKUP else "assign_delivery"
        await ShipmentTransitionService(self._session).transition(shipment, target, actor, action, request_id)
        return accepted

    async def confirm_pickup(self, task_id: UUID, actor: CurrentUser, request_id: str) -> CourierTask:
        """由接单快递员确认完成上门揽收。"""
        task = await self._get_task(task_id)
        if actor.role is not Role.COURIER or task.assignee_id != actor.id:
            raise AppError("FORBIDDEN_TASK_OWNER", "仅任务负责人可确认揽收", 403)
        if CourierTaskStatus(task.status) is not CourierTaskStatus.ACCEPTED:
            raise AppError("TASK_NOT_ACCEPTED", "任务尚未接单", 409)
        shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(task.shipment_id)
        task.status = CourierTaskStatus.COMPLETED
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.PICKED_UP, actor, "confirm_pickup", request_id)
        return task

    async def accept_dropoff(self, shipment_id: UUID, actor: CurrentUser, request_id: str) -> Shipment:
        """由始发网点验收客户自寄包裹。"""
        shipment = await self._require_origin_operator(shipment_id, actor)
        await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment.id)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.AT_ORIGIN_STATION, actor, "accept_dropoff", request_id)
        return shipment

    async def confirm_origin_arrival(self, shipment_id: UUID, actor: CurrentUser, request_id: str) -> Shipment:
        """由始发网点确认已揽收包裹到站。"""
        shipment = await self._require_origin_operator(shipment_id, actor)
        await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment.id)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.AT_ORIGIN_STATION, actor, "confirm_origin_arrival", request_id)
        return shipment

    async def list_pickup_tasks(self, shipment_id: UUID) -> list[CourierTask]:
        """返回运单的揽收任务，供后续任务列表接口使用。"""
        tasks = await self._session.scalars(select(CourierTask).where(CourierTask.shipment_id == shipment_id, CourierTask.task_type == CourierTaskType.PICKUP))
        return list(tasks)

    async def _require_origin_operator(self, shipment_id: UUID, actor: CurrentUser) -> Shipment:
        if actor.role is not Role.STATION_OPERATOR:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        shipment = await self._get_shipment(shipment_id)
        if shipment.origin_station_id is None:
            raise AppError("ORIGIN_STATION_REQUIRED", "运单缺少始发网点", 409)
        require_station_scope(shipment.origin_station_id, actor)
        return shipment

    async def _get_task(self, task_id: UUID) -> CourierTask:
        task = await self._session.get(CourierTask, task_id)
        if task is None:
            raise AppError("TASK_NOT_FOUND", "任务不存在", 404)
        return task

    async def _get_shipment(self, shipment_id: UUID) -> Shipment:
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        return shipment
