import httpx
import pytest

from yitu.knowledge.mineru_client import (
    MinerUClient,
    MinerUPermanentError,
    MinerURetryableError,
)


def make_http_client(handler: httpx.AsyncBaseTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="https://mineru.test")


@pytest.mark.asyncio
async def test_submit_and_poll_task() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": {"task_id": "task-1"}})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "task_id": "task-1",
                    "state": "done",
                    "full_zip_url": "https://cdn.test/result.zip?signature=secret",
                },
            },
        )

    api_client = make_http_client(httpx.MockTransport(handler))
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=make_http_client(httpx.MockTransport(handler)),
    )

    assert await client.submit("https://cos.test/source.pdf?signature=secret") == "task-1"
    task = await client.get_task("task-1")

    assert task.state == "done"
    assert task.full_zip_url == "https://cdn.test/result.zip?signature=secret"
    assert requests[0].headers["authorization"] == "Bearer test-token"
    assert requests[0].url.path == "/api/v4/extract/task"
    assert requests[1].url.path == "/api/v4/extract/task/task-1"
    await api_client.aclose()


@pytest.mark.asyncio
async def test_poll_processing_task() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"code": 0, "data": {"task_id": "task-2", "state": "running"}},
        )
    )
    api_client = make_http_client(transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=make_http_client(transport),
    )

    task = await client.get_task("task-2")

    assert task.state == "running"
    assert task.full_zip_url is None
    await api_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_retryable_http_errors_do_not_leak_request_data(status_code: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, text="sensitive upstream response")
    )
    api_client = make_http_client(transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=make_http_client(transport),
    )

    with pytest.raises(MinerURetryableError) as error:
        await client.submit("https://cos.test/source.pdf?signature=secret")

    assert "test-token" not in str(error.value)
    assert "signature" not in str(error.value)
    await api_client.aclose()


@pytest.mark.asyncio
async def test_permanent_error_for_rejected_or_invalid_response() -> None:
    responses = iter(
        [
            httpx.Response(400, text="request contains secret"),
            httpx.Response(200, text="not-json"),
        ]
    )
    transport = httpx.MockTransport(lambda request: next(responses))
    api_client = make_http_client(transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=make_http_client(transport),
    )

    with pytest.raises(MinerUPermanentError):
        await client.submit("https://cos.test/source.pdf?signature=secret")
    with pytest.raises(MinerUPermanentError):
        await client.get_task("task-1")
    await api_client.aclose()


@pytest.mark.asyncio
async def test_network_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    transport = httpx.MockTransport(handler)
    api_client = make_http_client(transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=make_http_client(transport),
    )

    with pytest.raises(MinerURetryableError, match="temporarily"):
        await client.get_task("task-1")
    await api_client.aclose()


@pytest.mark.asyncio
async def test_download_uses_client_without_authorization_header() -> None:
    authorization_headers: list[str | None] = []

    def download_handler(request: httpx.Request) -> httpx.Response:
        authorization_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, content=b"zip-data")

    api_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 0, "data": {}})
    )
    download_transport = httpx.MockTransport(download_handler)
    api_client = make_http_client(api_transport)
    download_client = make_http_client(download_transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=download_client,
    )

    assert await client.download_result("https://cdn.test/result.zip") == b"zip-data"
    assert authorization_headers == [None]
    await api_client.aclose()
    await download_client.aclose()


@pytest.mark.asyncio
async def test_download_error_does_not_retain_signed_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("download failed", request=request)

    transport = httpx.MockTransport(handler)
    api_client = make_http_client(transport)
    download_client = make_http_client(transport)
    client = MinerUClient(
        "https://mineru.test",
        "test-token",
        api_client=api_client,
        download_client=download_client,
    )

    with pytest.raises(MinerURetryableError) as error:
        await client.download_result("https://cdn.test/result.zip?signature=secret")

    assert error.value.__cause__ is None
    assert "signature" not in str(error.value)
    await api_client.aclose()
    await download_client.aclose()
