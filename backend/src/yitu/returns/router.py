from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session
from yitu.returns.schemas import RecoveryCommand, RecoveryShipmentView
from yitu.returns.service import ReturnService

router = APIRouter(prefix="/api/v1/returns", tags=["returns"])
_current_user = Depends(get_current_user)
_session = Depends(get_session)


@router.post("/shipments/{shipment_id}/cancel", response_model=RecoveryShipmentView)
async def cancel_shipment(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).cancel(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/request-interception", response_model=RecoveryShipmentView)
async def request_interception(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).request_interception(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/redeliver", response_model=RecoveryShipmentView)
async def redeliver(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).redeliver(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/convert-to-pickup", response_model=RecoveryShipmentView)
async def convert_to_pickup(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).convert_to_pickup(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/approve-return", response_model=RecoveryShipmentView)
async def approve_return(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).approve_return(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result


@router.post("/shipments/{shipment_id}/advance-return", response_model=RecoveryShipmentView)
async def advance_return(
    shipment_id: UUID,
    command: RecoveryCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> RecoveryShipmentView:
    result = await ReturnService(session).advance_return(
        shipment_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return result
