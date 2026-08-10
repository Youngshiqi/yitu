from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask
from yitu.dispatch.service import DispatchService
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session
from yitu.platform.errors import AppError
from yitu.shipments.credentials import LastMileService
from yitu.shipments.linehaul import LinehaulResult, LinehaulService
from yitu.shipments.service import ShipmentView

router = APIRouter(prefix="/api/v1/dispatch", tags=["dispatch"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


class DeliveryConfirmationRequest(BaseModel):
    """派送签收时由快递员提交的签收人姓名。"""

    signer_name: str


class PickupVerificationRequest(BaseModel):
    """网点核验时提交的一次性取件码。"""

    code: str


@router.post("/tasks/{task_id}/accept")
async def accept_task(task_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> None:
    await DispatchService(session).accept_task(task_id, user, f"accept:{task_id}")
    await session.commit()


@router.post("/tasks/{task_id}/confirm-pickup")
async def confirm_pickup(task_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> None:
    await DispatchService(session).confirm_pickup(task_id, user, f"pickup:{task_id}")
    await session.commit()


@router.post("/shipments/{shipment_id}/accept-dropoff", response_model=ShipmentView)
async def accept_dropoff(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> ShipmentView:
    shipment = await DispatchService(session).accept_dropoff(shipment_id, user, f"dropoff:{shipment_id}")
    await session.commit()
    return ShipmentView.model_validate(shipment)


@router.post("/shipments/{shipment_id}/confirm-origin-arrival", response_model=ShipmentView)
async def confirm_origin_arrival(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> ShipmentView:
    shipment = await DispatchService(session).confirm_origin_arrival(shipment_id, user, f"arrival:{shipment_id}")
    await session.commit()
    return ShipmentView.model_validate(shipment)


@router.post("/shipments/{shipment_id}/dispatch-linehaul", response_model=LinehaulResult)
async def dispatch_linehaul(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> LinehaulResult:
    result = await LinehaulService(session).dispatch_linehaul(shipment_id, user, f"dispatch-linehaul:{shipment_id}")
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/arrive-destination", response_model=LinehaulResult)
async def arrive_destination(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> LinehaulResult:
    result = await LinehaulService(session).arrive_destination(shipment_id, user, f"arrive-destination:{shipment_id}")
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/start-delivery", status_code=status.HTTP_204_NO_CONTENT)
async def start_delivery(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> Response:
    await LastMileService(session).start_delivery(shipment_id, user, f"start-delivery:{shipment_id}")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks")
async def list_tasks(shipment_id: UUID | None = None, user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[dict[str, object]]:
    query = select(CourierTask)
    if user.role in {Role.COURIER, Role.STATION_OPERATOR}:
        if user.station_id is None:
            raise AppError("STATION_SCOPE_REQUIRED", "当前身份缺少所属网点", 403)
        query = query.where(CourierTask.station_id == user.station_id)
    elif user.role is not Role.OPERATIONS_ADMIN:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
    if shipment_id is not None:
        query = query.where(CourierTask.shipment_id == shipment_id)
    tasks = list((await session.scalars(query)).all())
    return [{"id": task.id, "shipment_id": task.shipment_id, "task_type": task.task_type, "status": task.status, "assignee_id": task.assignee_id} for task in tasks]


@router.post("/shipments/{shipment_id}/confirm-delivery", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_delivery(shipment_id: UUID, payload: DeliveryConfirmationRequest, user: CurrentUser = _current_user, session: AsyncSession = _session) -> Response:
    await LastMileService(session).confirm_delivery(shipment_id, user, payload.signer_name, f"confirm-delivery:{shipment_id}")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/shipments/{shipment_id}/issue-pickup-credential", status_code=status.HTTP_204_NO_CONTENT)
async def issue_pickup_credential(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> Response:
    await LastMileService(session).issue_pickup_credential(shipment_id, user, f"issue-pickup:{shipment_id}")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/shipments/{shipment_id}/verify-station-pickup", status_code=status.HTTP_204_NO_CONTENT)
async def verify_station_pickup(shipment_id: UUID, payload: PickupVerificationRequest, user: CurrentUser = _current_user, session: AsyncSession = _session) -> Response:
    await LastMileService(session).verify_station_pickup(shipment_id, user, payload.code, f"verify-pickup:{shipment_id}")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
