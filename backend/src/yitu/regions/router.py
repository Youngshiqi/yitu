from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.database import get_session
from yitu.regions.models import RegionLevel
from yitu.regions.schemas import RegionListResponse, RegionView
from yitu.regions.service import list_regions

router = APIRouter(prefix="/api/v1/regions", tags=["regions"])
_session = Depends(get_session)


@router.get("", response_model=RegionListResponse)
async def get_regions(
    level: Annotated[RegionLevel | None, Query()] = None,
    parent_id: Annotated[UUID | None, Query()] = None,
    session: AsyncSession = _session,
) -> RegionListResponse:
    """为客户端省、市、区县级联选择提供按需数据。"""
    items = await list_regions(session, level=level, parent_id=parent_id)
    return RegionListResponse(items=[RegionView.model_validate(item) for item in items])
