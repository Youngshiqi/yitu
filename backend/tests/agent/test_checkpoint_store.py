"""checkpointer 生命周期与 thread 清理行为。"""

from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from yitu.agent import checkpoint_store
from yitu.agent.checkpoint_store import (
    _reset_for_tests,
    get_shared_checkpointer,
)
from yitu.agent.service import _clear_thread
from yitu.platform.config import get_settings


@pytest.fixture(autouse=True)
async def _clean_state() -> Any:
    """每个用例前后都重置模块级缓存，避免后端切换互相污染。"""
    await _reset_for_tests()
    yield
    await _reset_for_tests()


@pytest.mark.asyncio
async def test_memory_backend_returns_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "agent_checkpointer_backend", "memory")
    first = await get_shared_checkpointer()
    second = await get_shared_checkpointer()
    assert isinstance(first, MemorySaver)
    assert first is second


@pytest.mark.asyncio
async def test_postgres_backend_shared_and_persistent() -> None:
    """默认 postgres 后端：单例共享，且 checkpoint 可跨实例读取。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    first = await get_shared_checkpointer()
    second = await get_shared_checkpointer()
    assert isinstance(first, AsyncPostgresSaver)
    assert first is second

    # 写入一个 checkpoint，用全新 saver 实例（模拟另一副本）验证可读、可删。
    from langgraph.graph import END, START, StateGraph

    graph = (
        StateGraph(dict)
        .add_node("echo", lambda state: {"done": True})
        .add_edge(START, "echo")
        .add_edge("echo", END)
        .compile(checkpointer=first)
    )
    thread_id = "checkpoint-store-test"
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke({"input": 1}, config=config)

    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    from yitu.agent.checkpoint_store import _conn_info_from_settings

    pool = AsyncConnectionPool(
        _conn_info_from_settings(),
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        other = AsyncPostgresSaver(pool)
        tuple_ = await other.aget_tuple(config)
        assert tuple_ is not None
        await _clear_thread(other, thread_id)
        assert await other.aget_tuple(config) is None
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_clear_thread_prefers_async_delete() -> None:
    calls: list[str] = []

    class FakeSaver:
        async def adelete_thread(self, thread_id: str) -> None:
            calls.append(f"async:{thread_id}")

        def delete_thread(self, thread_id: str) -> None:
            calls.append(f"sync:{thread_id}")

    await _clear_thread(FakeSaver(), "t1")
    assert calls == ["async:t1"]


@pytest.mark.asyncio
async def test_clear_thread_falls_back_to_sync_delete() -> None:
    calls: list[str] = []

    class SyncOnlySaver:
        def delete_thread(self, thread_id: str) -> None:
            calls.append(f"sync:{thread_id}")

    await _clear_thread(SyncOnlySaver(), "t2")
    assert calls == ["sync:t2"]


def test_conn_info_strips_asyncpg_driver() -> None:
    assert checkpoint_store._conn_info_from_settings().startswith("postgresql://")
    assert "asyncpg" not in checkpoint_store._conn_info_from_settings()
