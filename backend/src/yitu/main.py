from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from yitu.addresses.router import router as addresses_router
from yitu.dispatch.router import router as dispatch_router
from yitu.identity.router import router as identity_router
from yitu.platform.config import get_settings
from yitu.platform.database import SessionFactory, dispose_database
from yitu.platform.errors import AppError
from yitu.platform.readiness import check_readiness
from yitu.platform.schemas import ErrorResponse
from yitu.pricing.router import router as pricing_router
from yitu.shipments.router import router as shipments_router
from yitu.stations.router import router as stations_router


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


class ReadinessResponse(BaseModel):
    """就绪检查响应。"""

    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """在演示环境准备固定身份，并在退出前释放异步数据库连接。"""
    if get_settings().app_profile == "demo":
        from yitu.demo.seed import seed_demo_users

        async with SessionFactory() as session, session.begin():
            await seed_demo_users(session)
    try:
        yield
    finally:
        await dispose_database()


def create_app() -> FastAPI:
    """创建并配置 Yitu API 应用。"""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(identity_router)
    app.include_router(stations_router)
    app.include_router(addresses_router)
    app.include_router(dispatch_router)
    app.include_router(shipments_router)
    app.include_router(pricing_router)

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

    @app.get("/api/v1/readiness", response_model=ReadinessResponse, tags=["system"])
    async def readiness() -> ReadinessResponse:
        try:
            await check_readiness()
        # 就绪接口只返回稳定错误契约，具体连接异常保留在异常链中。
        except Exception as error:
            raise AppError(
                code="SERVICE_NOT_READY",
                message="服务尚未就绪",
                status_code=503,
            ) from error
        return ReadinessResponse(status="ready")

    return app
