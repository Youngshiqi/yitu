from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.exceptions.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
from yitu.exceptions.schemas import (
    ExceptionAction,
    ExceptionAssign,
    ExceptionCreate,
    ExceptionListFilters,
    ExceptionListResponse,
    ExceptionResolve,
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


@router.post("/{case_id}/assign", response_model=ExceptionView)
async def assign_exception(
    case_id: UUID,
    command: ExceptionAssign,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    view = await ExceptionService(session).assign_case(
        case_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return view


@router.post("/{case_id}/start-processing", response_model=ExceptionView)
async def start_processing_exception(
    case_id: UUID,
    command: ExceptionAction,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    return await _apply_case_action(
        case_id,
        "start_processing",
        command,
        request,
        idempotency_key,
        user,
        session,
    )


@router.post("/{case_id}/wait-for-customer", response_model=ExceptionView)
async def wait_for_customer_exception(
    case_id: UUID,
    command: ExceptionAction,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    return await _apply_case_action(
        case_id,
        "wait_for_customer",
        command,
        request,
        idempotency_key,
        user,
        session,
    )


@router.post("/{case_id}/resume-processing", response_model=ExceptionView)
async def resume_processing_exception(
    case_id: UUID,
    command: ExceptionAction,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    return await _apply_case_action(
        case_id,
        "resume_processing",
        command,
        request,
        idempotency_key,
        user,
        session,
    )


@router.post("/{case_id}/resolve", response_model=ExceptionView)
async def resolve_exception(
    case_id: UUID,
    command: ExceptionResolve,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    view = await ExceptionService(session).resolve_case(
        case_id,
        command,
        user,
        idempotency_key,
        request.state.request_id,
    )
    await session.commit()
    return view


@router.post("/{case_id}/close", response_model=ExceptionView)
async def close_exception(
    case_id: UUID,
    command: ExceptionAction,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> ExceptionView:
    return await _apply_case_action(
        case_id,
        "close",
        command,
        request,
        idempotency_key,
        user,
        session,
    )


async def _apply_case_action(
    case_id: UUID,
    action: str,
    command: ExceptionAction,
    request: Request,
    idempotency_key: str,
    user: CurrentUser,
    session: AsyncSession,
) -> ExceptionView:
    view = await ExceptionService(session).apply_action(
        case_id,
        action,
        user,
        idempotency_key,
        request.state.request_id,
        reason=command.reason,
    )
    await session.commit()
    return view
