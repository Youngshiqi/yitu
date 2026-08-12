"""Agent 消息、工作和持久记忆的最小服务边界。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.models import AgentMemory
from yitu.agent.privacy import contains_forbidden_memory, redact_text
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError


class MemoryCreate(BaseModel):
    """只有用户明确确认后才允许提交的记忆内容。"""

    memory_type: str = Field(pattern=r"^(preference|instruction|profile)$")
    content: str = Field(min_length=1, max_length=1000)
    expires_at: datetime | None = None


class MemoryView(BaseModel):
    """持久记忆的公开字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memory_type: str
    content: str
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryService:
    """执行用户隔离、脱敏和显式确认的记忆增删改查。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, actor: CurrentUser) -> list[MemoryView]:
        rows = await self._session.scalars(
            select(AgentMemory)
            .where(AgentMemory.owner_id == actor.id, AgentMemory.active.is_(True))
            .order_by(AgentMemory.updated_at.desc(), AgentMemory.id)
        )
        now = Clock.now()
        return [
            MemoryView.model_validate(row)
            for row in rows.all()
            if row.expires_at is None or row.expires_at > now
        ]

    async def create(self, request: MemoryCreate, actor: CurrentUser) -> MemoryView:
        if contains_forbidden_memory(request.content):
            raise AppError("AGENT_MEMORY_SENSITIVE", "记忆不能保存密钥、令牌或联系方式", 422)
        now = Clock.now()
        row = AgentMemory(
            owner_id=actor.id,
            memory_type=request.memory_type,
            content=redact_text(request.content),
            active=True,
            expires_at=request.expires_at,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return MemoryView.model_validate(row)

    async def delete(self, memory_id: UUID, actor: CurrentUser) -> None:
        row = await self._session.scalar(
            select(AgentMemory).where(AgentMemory.id == memory_id, AgentMemory.owner_id == actor.id)
        )
        if row is None:
            raise AppError("AGENT_MEMORY_NOT_FOUND", "记忆不存在", 404)
        row.active = False
        row.updated_at = Clock.now()
        await self._session.flush()
