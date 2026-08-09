import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.errors import AppError


@dataclass(frozen=True)
class IdempotencyResponse:
    """表示可持久化并在后续请求中原样重放的 HTTP 响应快照。"""

    status_code: int
    body: object


def canonical_json_sha256(payload: object) -> str:
    """按稳定 JSON 编码计算请求体的 SHA-256 十六进制摘要。"""
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class IdempotencyService:
    """在调用方事务内仲裁并重放幂等请求的响应快照。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(
        self,
        scope: str,
        key: str,
        request_hash: str,
        operation: Callable[[], Awaitable[IdempotencyResponse]],
    ) -> IdempotencyResponse:
        """执行首次请求，或为相同请求哈希返回已保存的响应。"""
        # 事务锁先于查询获取，等待者会在获锁后看到竞争者已提交的记录。
        await self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended("
                "jsonb_build_array(CAST(:scope AS TEXT), CAST(:key AS TEXT))::text, "
                "0"
                ")"
                ")"
            ),
            {"scope": scope, "key": key},
        )
        existing_record = (
            await self._session.execute(
                text(
                    "SELECT request_hash, status, response_status, response_body "
                    "FROM idempotency_records "
                    "WHERE scope = :scope AND key = :key"
                ),
                {"scope": scope, "key": key},
            )
        ).mappings().one_or_none()

        if existing_record is not None:
            status = existing_record["status"]
            if status != "completed":
                raise RuntimeError(f"幂等记录状态异常: {status}")

            if existing_record["request_hash"] != request_hash:
                raise AppError(
                    code="IDEMPOTENCY_KEY_REUSED",
                    message="幂等键已用于不同的请求",
                    status_code=409,
                )

            response_status = existing_record["response_status"]
            response_body = existing_record["response_body"]
            if not isinstance(response_status, int) or response_body is None:
                raise RuntimeError("已完成的幂等记录响应不完整")
            return IdempotencyResponse(
                status_code=response_status,
                body=response_body,
            )

        response = await operation()
        response_body = json.dumps(
            response.body,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        await self._session.execute(
            text(
                "INSERT INTO idempotency_records ("
                "scope, key, request_hash, status, response_status, response_body, "
                "created_at, updated_at"
                ") VALUES ("
                ":scope, :key, :request_hash, 'completed', :response_status, "
                "CAST(:response_body AS JSONB), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "scope": scope,
                "key": key,
                "request_hash": request_hash,
                "response_status": response.status_code,
                "response_body": response_body,
            },
        )
        return response
