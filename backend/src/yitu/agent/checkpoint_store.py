"""LangGraph checkpointer 的生命周期管理。

多副本部署时进程级 MemorySaver 无法共享草稿 loop 的 thread 状态，
这里按配置切换为 AsyncPostgresSaver（共享 PostgreSQL），
并保留 memory 后端用于本地开发与单元测试。
"""

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver

from yitu.platform.config import get_settings

logger = logging.getLogger(__name__)

_memory_checkpointer: Any | None = None
_postgres_pool: Any | None = None
_postgres_checkpointer: Any | None = None
_init_lock = asyncio.Lock()
_compiled_runtime: Any | None = None


def _conn_info_from_settings() -> str:
    """把 SQLAlchemy 的 asyncpg URL 转换为 psycopg 可用的连接串。"""
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _open_postgres_checkpointer() -> tuple[Any, Any]:
    """创建连接池并执行幂等建表，返回 (pool, saver)。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        _conn_info_from_settings(),
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(cast(Any, pool))
    await saver.setup()
    return pool, saver


async def get_shared_checkpointer() -> Any:
    """返回进程级共享 checkpointer；postgres 后端懒初始化且仅初始化一次。"""
    global _memory_checkpointer, _postgres_pool, _postgres_checkpointer
    if _postgres_checkpointer is not None:
        return _postgres_checkpointer
    if get_settings().agent_checkpointer_backend == "memory":
        if _memory_checkpointer is None:
            _memory_checkpointer = MemorySaver()
        return _memory_checkpointer
    async with _init_lock:
        if _postgres_checkpointer is None:
            _postgres_pool, _postgres_checkpointer = await _open_postgres_checkpointer()
            logger.info("LangGraph checkpointer 已初始化为 AsyncPostgresSaver")
    return _postgres_checkpointer


async def get_shared_agent_runtime() -> Any:
    """根图与 checkpointer 进程级复用，请求级身份依赖仅通过 context 注入。"""
    global _compiled_runtime
    if _compiled_runtime is not None:
        return _compiled_runtime
    checkpointer = await get_shared_checkpointer()
    async with _init_lock:
        if _compiled_runtime is None:
            from yitu.agent.runtime.runtime import AgentRuntime
            from yitu.agent.workflows.assistant_graph import build_assistant_graph
            from yitu.agent.workflows.shipment_graph import build_shipment_graph

            child = build_shipment_graph()
            graph = build_assistant_graph(child, checkpointer=checkpointer)
            _compiled_runtime = AgentRuntime(graph)
    return _compiled_runtime


async def delete_thread(thread_id: UUID | str) -> None:
    """会话删除后同步删除工作流 checkpoint，避免保留可恢复状态。"""
    checkpointer = await get_shared_checkpointer()
    async_delete = getattr(checkpointer, "adelete_thread", None)
    if callable(async_delete):
        await async_delete(str(thread_id))
        return
    sync_delete = getattr(checkpointer, "delete_thread", None)
    if callable(sync_delete):
        sync_delete(str(thread_id))


async def dispose_checkpointer() -> None:
    """关闭 PostgreSQL 连接池，供应用或测试生命周期结束时调用。"""
    global _compiled_runtime, _postgres_pool, _postgres_checkpointer
    _compiled_runtime = None
    if _postgres_pool is not None:
        await _postgres_pool.close()
        _postgres_pool = None
        _postgres_checkpointer = None
        logger.info("LangGraph checkpointer 连接池已关闭")


async def _reset_for_tests() -> None:
    """重置模块级缓存并关闭遗留连接池，保证测试之间互不污染（仅测试使用）。"""
    global _compiled_runtime, _memory_checkpointer, _postgres_pool, _postgres_checkpointer
    if _postgres_pool is not None:
        try:
            await _postgres_pool.close()
        except Exception:  # noqa: BLE001, S110 - 测试清理不因池状态异常而中断
            pass
    _postgres_pool = None
    _postgres_checkpointer = None
    _memory_checkpointer = None
    _compiled_runtime = None
