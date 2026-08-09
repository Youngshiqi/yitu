import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.clock import Clock, to_business_timezone


@dataclass(frozen=True)
class AuditEntry:
    """表示写入后不可重新赋值的审计记录快照。"""

    id: int
    actor: str
    action: str
    resource: str
    before_summary: dict[str, object] | None
    after_summary: dict[str, object] | None
    reason: str | None
    request_id: str
    created_at: datetime


class AuditService:
    """只提供追加审计记录的能力，不暴露更新或删除接口。"""

    def __init__(self, session: AsyncSession, *, clock: Clock | None = None) -> None:
        self._session = session
        self._clock = clock or Clock()

    async def record(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        before_summary: dict[str, object] | None,
        after_summary: dict[str, object] | None,
        reason: str | None,
        request_id: str,
    ) -> AuditEntry:
        """在调用方事务中追加一条完整审计记录。"""
        created_at = self._clock.now()
        stored = (
            await self._session.execute(
                text(
                    "INSERT INTO audit_entries ("
                    "actor, action, resource, before_summary, after_summary, "
                    "reason, request_id, created_at"
                    ") VALUES ("
                    ":actor, :action, :resource, CAST(:before_summary AS JSONB), "
                    "CAST(:after_summary AS JSONB), :reason, :request_id, :created_at"
                    ") RETURNING id, created_at"
                ),
                {
                    "actor": actor,
                    "action": action,
                    "resource": resource,
                    "before_summary": _json_snapshot(before_summary),
                    "after_summary": _json_snapshot(after_summary),
                    "reason": reason,
                    "request_id": request_id,
                    "created_at": created_at,
                },
            )
        ).mappings().one()
        return AuditEntry(
            id=stored["id"],
            actor=actor,
            action=action,
            resource=resource,
            before_summary=before_summary,
            after_summary=after_summary,
            reason=reason,
            request_id=request_id,
            created_at=to_business_timezone(stored["created_at"]),
        )


def _json_snapshot(value: dict[str, object] | None) -> str | None:
    """把摘要编码为可写入 JSONB 的紧凑 JSON。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
