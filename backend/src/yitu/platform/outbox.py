import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
