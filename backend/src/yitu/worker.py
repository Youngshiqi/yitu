import asyncio
import atexit
from collections.abc import Coroutine
from typing import Any, TypeVar

from celery import Celery  # type: ignore[import-untyped]

from yitu.platform.config import get_settings
from yitu.platform.database import dispose_database

ResultT = TypeVar("ResultT")

_async_runner: asyncio.Runner | None = None


def run_async(operation: Coroutine[Any, Any, ResultT]) -> ResultT:
    """在 Worker 进程内复用事件循环，保护异步数据库连接池。"""
    global _async_runner
    if _async_runner is None:
        _async_runner = asyncio.Runner()
    return _async_runner.run(operation)


def close_async_runner() -> None:
    """关闭 Worker 的数据库连接池和事件循环。"""
    global _async_runner
    if _async_runner is None:
        return
    _async_runner.run(dispose_database())
    _async_runner.close()
    _async_runner = None


atexit.register(close_async_runner)

settings = get_settings()

celery_app = Celery(
    "yitu",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["yitu.platform.tasks", "yitu.sla.tasks", "yitu.notifications.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_default_exchange="yitu",
    task_default_queue="yitu",
    task_default_routing_key="yitu",
    task_serializer="json",
    worker_prefetch_multiplier=1,
    timezone=settings.business_timezone,
)
celery_app.conf.beat_schedule = {
    "relay-outbox-every-5-seconds": {
        "task": "yitu.relay_outbox",
        "schedule": 5.0,
    },
    "scan-sla-breaches-every-5-minutes": {
        "task": "yitu.scan_sla_breaches",
        "schedule": 300.0,
        "args": ("scheduled",),
    },
    "deliver-notifications-every-5-seconds": {
        "task": "yitu.deliver_notifications",
        "schedule": 5.0,
    },
}
