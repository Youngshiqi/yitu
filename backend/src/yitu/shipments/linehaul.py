from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_station_scope
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.enums import DeliveryMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.service import ShipmentTransitionService
from yitu.shipments.transport_models import TransportLeg, TransportLegStatus


class LinehaulResult(BaseModel):
    """干线动作返回的运单状态和下一步分支。"""

    shipment_id: UUID
    status: ShipmentStatus
    next_action: str | None = None


class LinehaulService:
    """执行始发发车、模拟干线到站和目标端分支。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def dispatch_linehaul(self, shipment_id: UUID, actor: CurrentUser, request_id: str) -> LinehaulResult:
        if actor.role is not Role.STATION_OPERATOR:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment_id)
        if shipment.origin_station_id is None:
            raise AppError("ORIGIN_STATION_REQUIRED", "运单缺少始发网点", 409)
        require_station_scope(shipment.origin_station_id, actor)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.IN_LINEHAUL, actor, "dispatch_linehaul", request_id)
        leg = TransportLeg(shipment_id=shipment.id, origin_station_id=shipment.origin_station_id, destination_station_id=shipment.destination_station_id, status=TransportLegStatus.IN_TRANSIT, started_at=Clock().now())
        self._session.add(leg)
        await self._session.flush()
        return LinehaulResult(shipment_id=shipment.id, status=ShipmentStatus.IN_LINEHAUL)

    async def arrive_destination(self, shipment_id: UUID, actor: CurrentUser, request_id: str) -> LinehaulResult:
        if actor.role not in {Role.OPERATIONS_ADMIN, Role.STATION_OPERATOR}:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment_id)
        if actor.role is Role.STATION_OPERATOR:
            if shipment.destination_station_id is None:
                raise AppError("DESTINATION_STATION_REQUIRED", "运单缺少目标网点", 409)
            require_station_scope(shipment.destination_station_id, actor)
        leg = await self._session.scalar(select(TransportLeg).where(TransportLeg.shipment_id == shipment.id, TransportLeg.status == TransportLegStatus.IN_TRANSIT))
        if leg is None:
            raise AppError("INVALID_SHIPMENT_TRANSITION", "不允许在干线发车前确认到站", 409)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.AT_DESTINATION_STATION, actor, "arrive_destination", request_id)
        leg.status = TransportLegStatus.ARRIVED
        leg.arrived_at = Clock().now()
        next_action: str | None = None
        if DeliveryMethod(shipment.delivery_method) is DeliveryMethod.HOME_DELIVERY:
            if shipment.destination_station_id is None:
                raise AppError("DESTINATION_STATION_REQUIRED", "运单缺少目标网点", 409)
            self._session.add(CourierTask(shipment_id=shipment.id, station_id=shipment.destination_station_id, task_type=CourierTaskType.DELIVERY, status=CourierTaskStatus.AVAILABLE))
            next_action = "CREATE_DELIVERY_TASK"
        else:
            next_action = "ISSUE_PICKUP_CREDENTIAL"
        await self._session.flush()
        return LinehaulResult(shipment_id=shipment.id, status=ShipmentStatus.AT_DESTINATION_STATION, next_action=next_action)

    async def _get_shipment(self, shipment_id: UUID) -> Shipment:
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        return shipment
