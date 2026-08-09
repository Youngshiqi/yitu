from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from yitu.main import create_app
from yitu.platform.errors import AppError
from yitu.platform.schemas import TimezoneAwareResponse


class TimestampResponse(TimezoneAwareResponse):
    occurred_at: datetime


async def test_app_error_returns_shared_error_contract() -> None:
    app: FastAPI = create_app()

    @app.get("/api/v1/test-error")
    async def raise_error() -> None:
        raise AppError(
            "INVALID_INPUT",
            "输入内容无效",
            422,
            details={"field": "name"},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/test-error")

    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_INPUT",
        "message": "输入内容无效",
        "request_id": response.headers["x-request-id"],
        "details": {"field": "name"},
    }


def test_response_model_normalizes_datetime_to_business_timezone() -> None:
    response = TimestampResponse(occurred_at=datetime(2026, 8, 9, tzinfo=UTC))

    assert response.model_dump(mode="json") == {
        "occurred_at": "2026-08-09T08:00:00+08:00"
    }
