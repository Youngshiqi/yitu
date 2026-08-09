from asyncio import run
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import text

from yitu.platform.database import SessionFactory
from yitu.platform.outbox import consume_once, relay_pending_events
from yitu.worker import celery_app

EventHandler = Callable[[dict[str, object], str], Awaitable[None]]
_handlers: dict[str, EventHandler] = {}


def register_event_handler(event_type: str, handler: EventHandler) -> None:
    """注册由具体业务模块提供的异步事件处理器。"""
    _handlers[event_type] = handler


@celery_app.task(name="yitu.relay_outbox")  # type: ignore[untyped-decorator]
def relay_outbox() -> int:
    """领取数据库中的到期事件并投递给 Celery。"""
    return run(relay_pending_events(SessionFactory, _publish_event))


async def _publish_event(event_id: UUID) -> None:
    """把事件 ID 发送给消费任务，可靠状态仍保存在 PostgreSQL。"""
    consume_outbox_event.delay(str(event_id))


@celery_app.task(name="yitu.consume_outbox_event")  # type: ignore[untyped-decorator]
def consume_outbox_event(event_id: str) -> bool:
    """在同步 Celery Worker 中运行异步数据库消费流程。"""
    return run(_consume_event(UUID(event_id)))


async def _consume_event(event_id: UUID) -> bool:
    async with SessionFactory() as session, session.begin():
        event_type = await session.scalar(
            text("SELECT event_type FROM outbox_events WHERE id = :event_id"),
            {"event_id": event_id},
        )
        if event_type is None:
            raise LookupError(f"Outbox 事件不存在: {event_id}")
        if not isinstance(event_type, str):
            raise TypeError("Outbox 事件类型无效")
        handler = _handlers.get(event_type)
        if handler is None:

            async def missing_handler(
                payload: dict[str, object], idempotency_key: str
            ) -> None:
                del payload, idempotency_key
                raise RuntimeError(f"未注册事件处理器: {event_type}")

            handler = missing_handler
        return await consume_once(session, event_id, handler)
