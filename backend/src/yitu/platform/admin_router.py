"""系统管理员运维接口。"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session
from yitu.platform.errors import AppError
from yitu.platform.outbox import DeadLetterService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
_current_user = Depends(get_current_user)
_session = Depends(get_session)


class DeadLetterView(BaseModel):
    """数据库死信任务视图。"""

    id: UUID
    event_id: UUID
    event_type: str
    business_id: str
    attempts: int
    last_error: str
    failed_at: datetime
    replayed_at: datetime | None
    suggested_action: str


class DeadLetterReplayView(BaseModel):
    """死信重放结果。"""

    dead_letter_id: UUID
    event_id: UUID
    status: str


@router.get("/dead-letters", response_model=list[DeadLetterView])
async def list_dead_letters(
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> list[DeadLetterView]:
    _require_system_admin(user)
    rows = (
        await session.execute(
            text(
                "SELECT id, event_id, event_type, business_id, attempts, "
                "last_error, failed_at, replayed_at, suggested_action "
                "FROM dead_letters ORDER BY failed_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"limit": min(max(limit, 1), 100), "offset": max(offset, 0)},
        )
    ).mappings().all()
    return [DeadLetterView.model_validate(dict(row)) for row in rows]


@router.post("/dead-letters/{dead_letter_id}/replay", response_model=DeadLetterReplayView)
async def replay_dead_letter(
    dead_letter_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> DeadLetterReplayView:
    _require_system_admin(user)
    try:
        event_id = await DeadLetterService(session).replay(dead_letter_id)
    except LookupError as error:
        raise AppError("DEAD_LETTER_NOT_FOUND", "死信记录不存在", 404) from error
    await session.commit()
    return DeadLetterReplayView(
        dead_letter_id=dead_letter_id,
        event_id=event_id,
        status="pending",
    )


def _require_system_admin(user: CurrentUser) -> None:
    if user.role is not Role.SYSTEM_ADMIN:
        raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
