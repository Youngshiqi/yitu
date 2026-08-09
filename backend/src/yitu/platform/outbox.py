import json
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yitu.platform.clock import Clock


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
