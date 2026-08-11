from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中读取应用运行所需的环境配置。"""

    app_name: str = "Yitu Logistics API"
    app_profile: str = "development"
    business_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    database_url: str = (
        "postgresql+asyncpg://yitu:yitu_test@127.0.0.1:55432/yitu_test"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    jwt_secret: str = "仅供本地开发的默认密钥，请在生产环境替换"
    jwt_expire_minutes: int = 30
    pickup_code_pepper: str = "仅供本地开发的取件码 pepper，请在生产环境替换"
    demo_pickup_code: str = "123456"
    knowledge_storage_backend: Literal["local", "s3"] = "local"
    knowledge_storage_root: str = "./var/knowledge"
    knowledge_max_upload_bytes: int = 20 * 1024 * 1024
    knowledge_s3_bucket: str = "yitu-knowledge"
    knowledge_s3_endpoint: str | None = None
    knowledge_s3_access_key: str | None = None
    knowledge_s3_secret_key: str | None = None
    knowledge_s3_region: str = "ap-guangzhou"
    embedding_provider: str = "local"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "bge-m3"
    embedding_dimension: int | None = None
    mineru_base_url: str = "https://mineru.net"
    mineru_token: str | None = None
    mineru_model_version: str = "vlm"

    model_config = SettingsConfigDict(env_prefix="YITU_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免同一进程重复读取环境变量。"""
    return Settings()
