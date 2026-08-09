import asyncio

from yitu.worker import close_async_runner, run_async


def test_worker_reuses_event_loop_between_tasks() -> None:
    """连续任务必须复用事件循环，避免 asyncpg 连接跨循环失效。"""

    async def current_loop_id() -> int:
        return id(asyncio.get_running_loop())

    try:
        first_loop_id = run_async(current_loop_id())
        second_loop_id = run_async(current_loop_id())
    finally:
        close_async_runner()

    assert second_loop_id == first_loop_id
