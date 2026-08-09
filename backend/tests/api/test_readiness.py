import pytest
from httpx import AsyncClient


async def test_readiness_reports_ready(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """依赖可用时返回稳定的就绪响应。"""

    async def dependencies_are_ready() -> None:
        return None

    monkeypatch.setattr("yitu.main.check_readiness", dependencies_are_ready)

    response = await client.get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize("dependency_error", [ConnectionError(), TimeoutError()])
async def test_readiness_reports_stable_error(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    dependency_error: Exception,
) -> None:
    """依赖不可用或超时时统一返回 503 错误契约。"""

    async def dependencies_are_not_ready() -> None:
        raise dependency_error

    monkeypatch.setattr("yitu.main.check_readiness", dependencies_are_not_ready)

    response = await client.get("/api/v1/readiness")

    assert response.status_code == 503
    body = response.json()
    assert body == {
        "code": "SERVICE_NOT_READY",
        "message": "服务尚未就绪",
        "request_id": body["request_id"],
        "details": None,
    }
    assert response.headers["X-Request-ID"] == body["request_id"]
