from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.service import DispatchService
from yitu.exceptions.service import ExceptionService
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user, require_resource_owner
from yitu.labels.service import LabelProjection, LabelService
from yitu.platform.database import get_session
from yitu.platform.errors import AppError
from yitu.shipments.enums import PickupMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.schemas import (
    CreateShipmentCommand,
    ShipmentResumeCommand,
    ShipmentResumeView,
)
from yitu.shipments.service import (
    ShipmentApplicationService,
    ShipmentListResponse,
    ShipmentReadView,
    ShipmentTransitionService,
    ShipmentView,
)
from yitu.tracking.schemas import TrackingEventView
from yitu.tracking.service import list_tracking_events

router = APIRouter(prefix="/api/v1/shipments", tags=["shipments"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


@router.post("", response_model=ShipmentView, status_code=status.HTTP_201_CREATED)
async def create_shipment(command: CreateShipmentCommand, idempotency_key: str = Header(alias="Idempotency-Key"), user: CurrentUser = _current_user, session: AsyncSession = _session) -> ShipmentView:
    if user.role is not Role.CUSTOMER:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
    result = await ShipmentApplicationService(session).create(command, user, idempotency_key)
    await session.commit()
    return result


@router.get("", response_model=ShipmentListResponse)
async def list_shipments(
    shipment_status: Annotated[
        ShipmentStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ShipmentListResponse:
    return await ShipmentApplicationService(session).list(
        user,
        shipment_status=shipment_status,
        limit=limit,
        offset=offset,
    )


@router.post("/{shipment_id}/confirm-payment", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_payment(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> Response:
    if user.role is not Role.CUSTOMER:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
    shipment = await session.get(Shipment, shipment_id)
    if shipment is None:
        raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
    require_resource_owner(shipment.owner_id, user)
    pickup_method = PickupMethod(shipment.pickup_method)
    target = ShipmentStatus.PENDING_PICKUP if pickup_method is PickupMethod.DOOR_PICKUP else ShipmentStatus.WAITING_FOR_DROPOFF
    await ShipmentTransitionService(session).transition(shipment, target, user, "confirm_payment", f"payment:{shipment_id}")
    if pickup_method is PickupMethod.DOOR_PICKUP:
        if shipment.origin_station_id is None:
            raise AppError("ORIGIN_STATION_REQUIRED", "运单缺少始发网点", 409)
        await DispatchService(session).create_pickup_task(shipment, shipment.origin_station_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{shipment_id}", response_model=ShipmentReadView)
async def get_shipment(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> ShipmentReadView:
    """Return shipment detail within the actor's visibility scope."""
    result = await ShipmentApplicationService(session).get_detail(shipment_id, user)
    if result is None:
        raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
    return result


@router.get("/{shipment_id}/tracking", response_model=list[TrackingEventView])
async def get_tracking(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[TrackingEventView]:
    """按顺序返回客户本人可见的运单轨迹。"""
    if user.role is not Role.CUSTOMER:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
    shipment = await session.get(Shipment, shipment_id)
    if shipment is None:
        raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
    require_resource_owner(shipment.owner_id, user)
    return [TrackingEventView.model_validate(event) for event in await list_tracking_events(session, shipment_id)]


@router.get("/{shipment_id}/label", response_model=LabelProjection)
async def get_label(
    shipment_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> LabelProjection:
    shipment = await session.get(Shipment, shipment_id)
    if shipment is None:
        raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
    if user.role is Role.CUSTOMER:
        require_resource_owner(shipment.owner_id, user)
    elif user.role is not Role.OPERATIONS_ADMIN:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
    return await LabelService(session).project(shipment_id)


@router.post("/{shipment_id}/resume", response_model=ShipmentResumeView)
async def resume_shipment(
    shipment_id: UUID,
    command: ShipmentResumeCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ShipmentResumeView:
    view = await ExceptionService(session).resume_shipment(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return view
