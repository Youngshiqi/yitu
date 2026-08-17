"""语义记忆契约：向量写入、降级策略、相关性与 recency 兜底召回。"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from yitu.agent.memory import MemoryCreate, MemoryService
from yitu.agent.models import AgentMemory
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.database import SessionFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")


DIM = 1024  # 与 AgentMemory.embedding 的真实 pgvector 列维度一致。


def _unit_vector(axis: int) -> list[float]:
    vector = [0.0] * DIM
    vector[axis] = 1.0
    return vector


_DIAGONAL = [((2.0**0.5) / 2.0)] * DIM


class SameTextEmbedding:
    """任何文本生成相同单位向量的确定性实现，用于验证降级与兜底逻辑。"""

    model = "semantic-test"
    dimension = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_unit_vector(0) for _ in texts]


class KeywordEmbedding:
    """按关键词生成正交单位向量：命中关键词的记忆与查询 cosine 距离为 0。"""

    model = "semantic-test"
    dimension = DIM

    def __init__(self, keywords: list[str]) -> None:
        self._keywords = keywords
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        for index, keyword in enumerate(self._keywords):
            if keyword in text:
                return _unit_vector(index)
        return list(_DIAGONAL)


class BrokenEmbedding:
    model = "semantic-test"
    dimension = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding service down")


async def _owner() -> CurrentUser:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        row = next(user for user in users if user.demo_key == "customer")
    return CurrentUser(row.id, Role.CUSTOMER, None)


async def _cleanup(owner_id) -> None:
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(AgentMemory).where(AgentMemory.owner_id == owner_id))


async def test_create_stores_embedding_and_model() -> None:
    owner = await _owner()
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=SameTextEmbedding())
            view = await service.create(
                MemoryCreate(memory_type="preference", content="工作日白天收件"), owner
            )
        async with SessionFactory() as session:
            row = await session.get(AgentMemory, view.id)
            assert row is not None
            assert row.embedding is not None
            assert len(row.embedding) == DIM
            assert row.embedding_model == "semantic-test"
    finally:
        await _cleanup(owner.id)


async def test_create_survives_embedding_failure() -> None:
    """向量服务故障时记忆仍必须写入成功，embedding 落 NULL。"""
    owner = await _owner()
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=BrokenEmbedding())
            view = await service.create(
                MemoryCreate(memory_type="profile", content="常用寄件城市：上海"), owner
            )
            assert view.content == "常用寄件城市：上海"
        async with SessionFactory() as session:
            row = await session.get(AgentMemory, view.id)
            assert row is not None
            assert row.embedding is None
            assert row.embedding_model is None
    finally:
        await _cleanup(owner.id)


async def test_recall_ranks_by_semantic_relevance() -> None:
    """与查询语义相关的记忆排在 recency 之前。"""
    owner = await _owner()
    provider = KeywordEmbedding(["包装", "地址"])
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=provider)
            # 先创建一条更"新"但不相关的记忆，再创建相关记忆。
            await service.create(
                MemoryCreate(memory_type="preference", content="收件地址用公司前台"), owner
            )
            await service.create(
                MemoryCreate(memory_type="preference", content="易碎品需要加固包装"), owner
            )
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=provider)
            results = await service.recall(owner.id, query="玻璃杯怎么包装寄快递")
        assert results[0] == "易碎品需要加固包装"
    finally:
        await _cleanup(owner.id)


async def test_recall_falls_back_to_recency_without_embeddings() -> None:
    """无向量行（存量/降级）按更新时间倒序兜底，行为与旧版一致。"""
    owner = await _owner()
    try:
        async with SessionFactory() as session, session.begin():
            now = Clock.now()
            session.add_all(
                [
                    AgentMemory(
                        owner_id=owner.id,
                        memory_type="preference",
                        content="旧记忆",
                        active=True,
                        created_at=now - timedelta(hours=2),
                        updated_at=now - timedelta(hours=2),
                    ),
                    AgentMemory(
                        owner_id=owner.id,
                        memory_type="preference",
                        content="新记忆",
                        active=True,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=SameTextEmbedding())
            results = await service.recall(owner.id, query="任意查询")
        assert results == ["新记忆", "旧记忆"]
    finally:
        await _cleanup(owner.id)


async def test_recall_with_broken_query_embedding_uses_recency() -> None:
    """查询嵌入失败时退化为纯 recency 排序，不抛错。"""
    owner = await _owner()
    provider = BrokenEmbedding()
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=SameTextEmbedding())
            await service.create(
                MemoryCreate(memory_type="preference", content="周日不收件"), owner
            )
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=provider)
            results = await service.recall(owner.id, query="什么时候收件")
        assert results == ["周日不收件"]
    finally:
        await _cleanup(owner.id)


async def test_recall_excludes_expired_and_inactive() -> None:
    owner = await _owner()
    provider = SameTextEmbedding()
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=provider)
            await service.create(
                MemoryCreate(
                    memory_type="preference",
                    content="已过期记忆",
                    expires_at=Clock.now() - timedelta(minutes=1),
                ),
                owner,
            )
            valid = await service.create(
                MemoryCreate(memory_type="preference", content="有效记忆"), owner
            )
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=provider)
            results = await service.recall(owner.id, query="记忆")
        assert results == ["有效记忆"]
        # 软删除后同样不可召回。
        async with SessionFactory() as session, session.begin():
            await MemoryService(session).delete(valid.id, owner)
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=provider)
            assert await service.recall(owner.id, query="记忆") == []
    finally:
        await _cleanup(owner.id)


async def test_recall_is_isolated_per_owner() -> None:
    """记忆严格按 owner 隔离，其他用户查询不可见。"""
    owner = await _owner()
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        other_row = next(user for user in users if user.demo_key == "operations")
    other = CurrentUser(other_row.id, Role.OPERATIONS_ADMIN, None)
    try:
        async with SessionFactory() as session, session.begin():
            service = MemoryService(session, embedding_provider=SameTextEmbedding())
            await service.create(
                MemoryCreate(memory_type="preference", content="客户专属偏好"), owner
            )
        async with SessionFactory() as session:
            service = MemoryService(session, embedding_provider=SameTextEmbedding())
            assert await service.recall(other.id, query="偏好") == []
    finally:
        await _cleanup(owner.id)
