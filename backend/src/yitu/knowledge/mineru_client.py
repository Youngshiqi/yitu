from dataclasses import dataclass
from typing import Any, Self

import httpx


@dataclass(frozen=True, slots=True)
class MinerUTask:
    """MinerU 异步解析任务的稳定领域视图。"""

    task_id: str
    state: str
    full_zip_url: str | None
    error_message: str | None


class MinerURetryableError(RuntimeError):
    """表示限流、服务端故障或网络异常，可由 Worker 延迟重试。"""


class MinerUPermanentError(RuntimeError):
    """表示请求或响应不可恢复，重试不会改变结果。"""


class MinerUClient:
    """调用 MinerU v4 异步解析 API，并隔离认证请求与产物下载。"""

    def __init__(
        self,
        base_url: str,
        token: str,
        model_version: str = "vlm",
        *,
        api_client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not token:
            raise ValueError("MinerU token is required")

        self._model_version = model_version
        self._authorization = f"Bearer {token}"
        self._owns_api_client = api_client is None
        self._owns_download_client = download_client is None
        self._api_client = api_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        # 下载地址通常属于 CDN，必须使用没有 MinerU 认证头的独立客户端。
        self._download_client = download_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """只关闭由当前实例创建的 HTTP 客户端。"""
        if self._owns_api_client:
            await self._api_client.aclose()
        if self._owns_download_client:
            await self._download_client.aclose()

    async def submit(self, source_url: str) -> str:
        """提交临时 COS URL，返回可持久化的 MinerU 任务 ID。"""
        response = await self._request(
            self._api_client,
            "POST",
            "/api/v4/extract/task",
            headers={"Authorization": self._authorization},
            json={"url": source_url, "model_version": self._model_version},
        )
        data = self._response_data(response)
        task_id = data.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise MinerUPermanentError("MinerU response is missing task_id")
        return task_id

    async def get_task(self, task_id: str) -> MinerUTask:
        """查询任务状态，并仅暴露后续工作流需要的字段。"""
        response = await self._request(
            self._api_client,
            "GET",
            f"/api/v4/extract/task/{task_id}",
            headers={"Authorization": self._authorization},
        )
        data = self._response_data(response)
        state = data.get("state")
        if not isinstance(state, str) or not state:
            raise MinerUPermanentError("MinerU response is missing task state")

        response_task_id = data.get("task_id", task_id)
        if not isinstance(response_task_id, str) or not response_task_id:
            raise MinerUPermanentError("MinerU response has invalid task_id")

        full_zip_url = data.get("full_zip_url")
        if full_zip_url is not None and not isinstance(full_zip_url, str):
            raise MinerUPermanentError("MinerU response has invalid result URL")

        error_message = data.get("err_msg", data.get("error_message"))
        if error_message is not None and not isinstance(error_message, str):
            error_message = "MinerU task failed"

        return MinerUTask(
            task_id=response_task_id,
            state=state,
            full_zip_url=full_zip_url,
            error_message=error_message,
        )

    async def download_result(self, url: str) -> bytes:
        """使用无认证客户端下载 MinerU 解析产物 ZIP。"""
        response = await self._request(self._download_client, "GET", url)
        return response.content

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.RequestError:
            # httpx 异常包含完整请求 URL；下载地址带签名时不可保留异常链。
            raise MinerURetryableError("MinerU request failed temporarily") from None

        if response.status_code == 429 or response.status_code >= 500:
            raise MinerURetryableError("MinerU service is temporarily unavailable")
        if response.status_code >= 400:
            raise MinerUPermanentError("MinerU rejected the request")
        return response

    @staticmethod
    def _response_data(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MinerUPermanentError("MinerU returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MinerUPermanentError("MinerU returned an invalid response")

        code = payload.get("code", 0)
        if code not in (0, "0", None):
            raise MinerUPermanentError("MinerU API reported an error")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MinerUPermanentError("MinerU response is missing data")
        return data
