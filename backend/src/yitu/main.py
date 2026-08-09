from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


def create_app() -> FastAPI:
    """创建并配置 Yitu API 应用。"""
    app = FastAPI(title="Yitu Logistics API", version="0.1.0")

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app
