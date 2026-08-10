from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.service import DispatchService
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session
from yitu.shipments.service import ShipmentView

router = APIRouter(prefix="/api/v1/dispatch", tags=["dispatch"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


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
