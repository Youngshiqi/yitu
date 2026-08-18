import json
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yitu.platform.clock import Clock


class RetryPolicy:
    """计算失败任务的指数退避时间。"""

    @staticmethod
    def next_attempt(attempts: int, now: datetime, jitter: float) -> datetime:
        """返回带 0–10% 随机抖动且最长 30 分钟的下次尝试时间。"""
        if not 0 <= jitter <= 1:
            raise ValueError("jitter 必须位于 0 到 1 之间")
        delay_seconds = min(30 * (2 ** (attempts - 1)), 30 * 60)
        return now + timedelta(seconds=delay_seconds * (1 + jitter * 0.1))


class OutboxService:
    """在调用方事务内追加需要可靠投递的领域事件。"""

    def __init__(self, session: AsyncSession, *, clock: Clock | None = None) -> None:
        self._session = session
        self._clock = clock or Clock()

    async def append(
        self,
        *,
        event_type: str,
        business_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> UUID:
        """追加待投递事件，不在服务内部提交事务。"""
        event_id = uuid4()
        created_at = self._clock.now()
        await self._session.execute(
            text(
                "INSERT INTO outbox_events ("
                "id, event_type, business_id, payload, idempotency_key, status, "
                "attempts, next_attempt_at, created_at"
                ") VALUES ("
                ":id, :event_type, :business_id, CAST(:payload AS JSONB), "
                ":idempotency_key, 'pending', 0, :next_attempt_at, :created_at"
                ")"
            ),
            {
                "id": event_id,
                "event_type": event_type,
                "business_id": business_id,
                "payload": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "idempotency_key": idempotency_key,
                "next_attempt_at": created_at,
                "created_at": created_at,
            },
        )
        return event_id


async def relay_pending_events(
    session_factory: async_sessionmaker[AsyncSession],
    publish: Callable[[UUID], Awaitable[None]],
    *,
    limit: int = 100,
    clock: Clock | None = None,
) -> int:
    """领取并发布已经到期的待投递事件。"""
    now = (clock or Clock()).now()
    async with session_factory() as session, session.begin():
        event_ids = (
            await session.execute(
                text(
                    "SELECT id FROM outbox_events "
                    "WHERE status = 'pending' AND next_attempt_at <= :now "
                    "ORDER BY next_attempt_at, created_at "
                    "FOR UPDATE SKIP LOCKED LIMIT :limit"
                ),
                {"now": now, "limit": limit},
            )
        ).scalars().all()
        for event_id in event_ids:
            await publish(event_id)
            await session.execute(
                text(
                    "UPDATE outbox_events SET status = 'published' "
                    "WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )
    return len(event_ids)


async def consume_once(
    session: AsyncSession,
    event_id: UUID,
    handler: Callable[[dict[str, object], str], Awaitable[None]],
) -> bool:
    """使用数据库行锁保证同一事件的业务处理只成功执行一次。"""
    record = (
        await session.execute(
            text(
                "SELECT status, event_type, business_id, payload, idempotency_key, "
                "attempts FROM outbox_events "
                "WHERE id = :event_id FOR UPDATE"
            ),
            {"event_id": event_id},
        )
    ).mappings().one_or_none()
    if record is None:
        raise LookupError(f"Outbox 事件不存在: {event_id}")
    if record["status"] in {"completed", "dead"}:
        return False
    if record["status"] != "published":
        raise RuntimeError(f"Outbox 事件状态不可消费: {record['status']}")

    payload = record["payload"]
    idempotency_key = record["idempotency_key"]
    if not isinstance(payload, dict) or not isinstance(idempotency_key, str):
        raise TypeError("Outbox 事件数据不完整")

    try:
        async with session.begin_nested():
            await handler(payload, idempotency_key)
    # Worker 必须把未知 handler 异常转成数据库中的可恢复状态。
    except Exception as error:  # noqa: BLE001
        await _record_failure(session, event_id, record, error)
        return False

    await session.execute(
        text(
            "UPDATE outbox_events SET status = 'completed', processed_at = :now "
            "WHERE id = :event_id"
        ),
        {"event_id": event_id, "now": Clock.now()},
    )
    return True


async def _record_failure(
    session: AsyncSession,
    event_id: UUID,
    record: RowMapping,
    error: Exception,
) -> None:
    """保存一次失败，达到第五次时转入数据库死信。"""
    attempts = int(record["attempts"]) + 1
    now = Clock.now()
    error_message = str(error)
    if attempts < 5:
        await session.execute(
            text(
                "UPDATE outbox_events SET status = 'pending', attempts = :attempts, "
                "next_attempt_at = :next_attempt_at, last_error = :last_error "
                "WHERE id = :event_id"
            ),
            {
                "event_id": event_id,
                "attempts": attempts,
                "next_attempt_at": RetryPolicy.next_attempt(
                    attempts,
                    now,
                    random.random(),
                ),
                "last_error": error_message,
            },
        )
        return

    await session.execute(
        text(
            "UPDATE outbox_events SET status = 'dead', attempts = :attempts, "
            "last_error = :last_error WHERE id = :event_id"
        ),
        {
            "event_id": event_id,
            "attempts": attempts,
            "last_error": error_message,
        },
    )
    await session.execute(
        text(
            "INSERT INTO dead_letters ("
            "id, event_id, event_type, business_id, payload, idempotency_key, "
            "attempts, last_error, failed_at, suggested_action"
            ") VALUES ("
            ":id, :event_id, :event_type, :business_id, CAST(:payload AS JSONB), "
            ":idempotency_key, :attempts, :last_error, :failed_at, :suggested_action"
            ")"
        ),
        {
            "id": uuid4(),
            "event_id": event_id,
            "event_type": record["event_type"],
            "business_id": record["business_id"],
            "payload": json.dumps(
                record["payload"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "idempotency_key": record["idempotency_key"],
            "attempts": attempts,
            "last_error": error_message,
            "failed_at": now,
            "suggested_action": "修复失败原因后由管理员重放",
        },
    )
