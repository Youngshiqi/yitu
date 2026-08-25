"""Agent 消息、工作和持久记忆的最小服务边界。"""

from __future__ import annotations

import asyncio
import builtins
import logging
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.domain.models import AgentMemory
from yitu.agent.infrastructure.privacy import contains_forbidden_memory, redact_text
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError

logger = logging.getLogger(__name__)

# 单轮注入上下文的记忆条数上限，与 context.build_model_context 保持一致。
MEMORY_RECALL_LIMIT = 10


class MemoryEmbeddingProvider(Protocol):
    """语义记忆所需的最小嵌入协议，与 knowledge.EmbeddingProvider 兼容。"""

    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _default_embedding_provider() -> MemoryEmbeddingProvider | None:
    """按运行配置解析嵌入服务；配置缺失时返回 None 走 recency 兜底。"""
    from yitu.knowledge.embedding import get_embedding_provider

    try:
        return get_embedding_provider()
    except RuntimeError:
        return None


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
    """执行用户隔离、脱敏和显式确认的记忆增删改查与语义召回。"""

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: MemoryEmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        # None 表示延迟解析运行配置；False 表示已确认不可用。
        self._embedding_provider = embedding_provider
        self._provider_resolved = embedding_provider is not None

    def _resolve_provider(self) -> MemoryEmbeddingProvider | None:
        if not self._provider_resolved:
            self._embedding_provider = _default_embedding_provider()
            self._provider_resolved = True
        return self._embedding_provider

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
            raise AppError(
                "AGENT_MEMORY_SENSITIVE", "记忆不能保存密钥、令牌或联系方式", 422
            )
        now = Clock.now()
        content = redact_text(request.content)
        embedding, embedding_model = await self._embed_content(content)
        row = AgentMemory(
            owner_id=actor.id,
            memory_type=request.memory_type,
            content=content,
            active=True,
            expires_at=request.expires_at,
            created_at=now,
            updated_at=now,
            embedding=embedding,
            embedding_model=embedding_model,
        )
        self._session.add(row)
        await self._session.flush()
        return MemoryView.model_validate(row)

    async def _embed_content(
        self, content: str
    ) -> tuple[builtins.list[float] | None, str | None]:
        """为记忆内容生成向量；任何失败都降级为 NULL，不阻塞记忆创建。"""
        provider = self._resolve_provider()
        if provider is None:
            return None, None
        try:
            vector = (await asyncio.to_thread(provider.embed, [content]))[0]
        except Exception:
            logger.warning("记忆向量生成失败，降级为 recency 召回", exc_info=True)
            return None, None
        return vector, provider.model

    async def recall(
        self, owner_id: UUID, query: str | None, limit: int = MEMORY_RECALL_LIMIT
    ) -> builtins.list[str]:
        """按与当前用户消息的语义相关性召回记忆。

        排序策略：有余量向量且查询嵌入成功时按 cosine 距离升序；
        无向量行（存量/降级）以 NULLS LAST 落到尾部按更新时间兜底。
        查询为空或嵌入失败时退化为纯 recency 排序，行为与旧版一致。
        """
        statement = (
            select(AgentMemory)
            .where(
                AgentMemory.owner_id == owner_id,
                AgentMemory.active.is_(True),
                (AgentMemory.expires_at.is_(None))
                | (AgentMemory.expires_at > Clock.now()),
            )
            .order_by(AgentMemory.updated_at.desc(), AgentMemory.id)
            .limit(limit)
        )
        if query:
            query_vector = await self._embed_query(query)
            if query_vector is not None:
                statement = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.owner_id == owner_id,
                        AgentMemory.active.is_(True),
                        (AgentMemory.expires_at.is_(None))
                        | (AgentMemory.expires_at > Clock.now()),
                    )
                    .order_by(
                        AgentMemory.embedding.cosine_distance(query_vector)
                        .asc()
                        .nulls_last(),
                        AgentMemory.updated_at.desc(),
                        AgentMemory.id,
                    )
                    .limit(limit)
                )
        rows = await self._session.scalars(statement)
        return [row.content for row in rows.all()]

    async def _embed_query(self, query: str) -> builtins.list[float] | None:
        provider = self._resolve_provider()
        if provider is None:
            return None
        try:
            return (await asyncio.to_thread(provider.embed, [query]))[0]
        except Exception:
            logger.warning("记忆查询向量生成失败，回退 recency 召回", exc_info=True)
            return None

    async def delete(self, memory_id: UUID, actor: CurrentUser) -> None:
        row = await self._session.scalar(
            select(AgentMemory).where(
                AgentMemory.id == memory_id, AgentMemory.owner_id == actor.id
            )
        )
        if row is None:
            raise AppError("AGENT_MEMORY_NOT_FOUND", "记忆不存在", 404)
        row.active = False
        row.updated_at = Clock.now()
        await self._session.flush()
