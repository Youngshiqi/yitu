"""SLA HTTP 接口。"""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import (
    CurrentUser,
    get_current_user,
    require_resource_owner,
    require_roles,
)
from yitu.platform.database import get_session
from yitu.platform.errors import AppError
from yitu.sla.models import SLAInstance, SLARule
from yitu.sla.schemas import (
    ETAUpdateRequest,
    SLAInstanceStart,
    SLAInstanceView,
    SLAPauseRequest,
    SLARuleCreate,
    SLARuleView,
)
from yitu.sla.service import SLAService

router = APIRouter(prefix="/api/v1/sla", tags=["sla"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)
_operators = Depends(require_roles(Role.OPERATIONS_ADMIN, Role.SYSTEM_ADMIN))


@router.post("/rules", response_model=SLARuleView, status_code=status.HTTP_201_CREATED)
async def create_rule(payload: SLARuleCreate, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLARule:
    """仅运营管理员可发布 SLA 规则。"""
    del user
    rule = SLARule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.post("/shipments/{shipment_id}/instances", response_model=SLAInstanceView, status_code=status.HTTP_201_CREATED)
async def start_instance(shipment_id: UUID, payload: SLAInstanceStart, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLAInstance:
    """为运单启动一个履约阶段 SLA。"""
    del user
    try:
        instance = await SLAService(session).start(shipment_id, payload.route_code, payload.stage, service_type=payload.service_type)
    except ValueError as error:
        raise AppError(code="SLA_START_FAILED", message=str(error), status_code=400) from error
    await session.commit()
    return instance


@router.get("/shipments/{shipment_id}/instances", response_model=list[SLAInstanceView])
async def list_instances(shipment_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[SLAInstance]:
    """客户只可查看自己的 SLA，运营角色可以查看全部。"""
    instances = (await session.scalars(select(SLAInstance).where(SLAInstance.shipment_id == shipment_id))).all()
    for instance in instances:
        require_resource_owner(instance.owner_id, user)
    return list(instances)


@router.post("/instances/{instance_id}/pause", response_model=SLAInstanceView)
async def pause_instance(instance_id: UUID, payload: SLAPauseRequest, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLAInstance:
    """暂停 SLA 阶段。"""
    del user
    try:
        instance = await SLAService(session).pause(instance_id, payload.reason)
    except ValueError as error:
        raise AppError(code="SLA_PAUSE_FAILED", message=str(error), status_code=400) from error
    await session.commit()
    return instance


@router.post("/instances/{instance_id}/resume", response_model=SLAInstanceView)
async def resume_instance(instance_id: UUID, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLAInstance:
    """恢复 SLA 阶段。"""
    del user
    try:
        instance = await SLAService(session).resume(instance_id)
    except ValueError as error:
        raise AppError(code="SLA_RESUME_FAILED", message=str(error), status_code=400) from error
    await session.commit()
    return instance


@router.post("/instances/{instance_id}/complete", response_model=SLAInstanceView)
async def complete_instance(instance_id: UUID, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLAInstance:
    """完成 SLA 阶段。"""
    del user
    try:
        instance = await SLAService(session).complete(instance_id)
    except ValueError as error:
        raise AppError(code="SLA_COMPLETE_FAILED", message=str(error), status_code=400) from error
    await session.commit()
    return instance


@router.post("/instances/{instance_id}/eta", response_model=SLAInstanceView)
async def update_eta(instance_id: UUID, payload: ETAUpdateRequest, user: CurrentUser = _operators, session: AsyncSession = _session) -> SLAInstance:
    """更新 ETA，但不覆盖客户承诺时间。"""
    del user
    try:
        instance = await SLAService(session).update_eta(instance_id, timedelta(minutes=payload.delay_minutes))
    except ValueError as error:
        raise AppError(code="SLA_ETA_UPDATE_FAILED", message=str(error), status_code=400) from error
    await session.commit()
    return instance
