from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.exceptions.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
from yitu.exceptions.schemas import (
    ExceptionCreate,
    ExceptionListFilters,
    ExceptionListResponse,
    ExceptionView,
)
from yitu.exceptions.service import ExceptionService
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/exceptions", tags=["exceptions"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


@router.post("", response_model=ExceptionView, status_code=status.HTTP_201_CREATED)
async def open_exception(
    command: ExceptionCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    view = await ExceptionService(session).open_case(
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return view


@router.get("", response_model=ExceptionListResponse)
async def list_exceptions(
    shipment_id: UUID | None = None,
    status_filter: Annotated[ExceptionStatus | None, Query(alias="status")] = None,
    case_type: ExceptionType | None = None,
    severity: ExceptionSeverity | None = None,
    responsible_station_id: UUID | None = None,
    assigned_to: UUID | None = None,
    blocks_fulfillment: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionListResponse:
    filters = ExceptionListFilters(
        shipment_id=shipment_id,
        status=status_filter,
        case_type=case_type,
        severity=severity,
        responsible_station_id=responsible_station_id,
        assigned_to=assigned_to,
        blocks_fulfillment=blocks_fulfillment,
        limit=limit,
        offset=offset,
    )
    items, total = await ExceptionService(session).list_cases(user, filters)
    return ExceptionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{case_id}", response_model=ExceptionView)
async def get_exception(
    case_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    return await ExceptionService(session).get_case(case_id, user)
