from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from yitu.platform.config import get_settings
from yitu.platform.errors import AppError
from yitu.platform.schemas import ErrorResponse


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


def create_app() -> FastAPI:
    """创建并配置 Yitu API 应用。"""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.middleware("http")
    async def attach_request_id(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """为每个请求生成追踪标识，并在所有响应中返回该标识。"""
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        """将预期错误转换为稳定的客户端错误契约。"""
        response = ErrorResponse(
            code=error.code,
            message=error.message,
            request_id=request.state.request_id,
            details=error.details,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=response.model_dump(),
        )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app
