from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中读取应用运行所需的环境配置。"""

    app_name: str = "Yitu Logistics API"
    app_profile: str = "development"
    business_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    database_url: str = (
        "postgresql+asyncpg://yitu:请替换密码@127.0.0.1:55433/yitu"
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
    embedding_model: str = "qwen3.7-text-embedding"
    embedding_dimension: int | None = None
    mineru_base_url: str = "https://mineru.net"
    mineru_token: str | None = None
    mineru_model_version: str = "vlm"
    agent_model_provider: str = "fixed"
    agent_model_base_url: str | None = None
    agent_model_api_key: str | None = None
    agent_model_name: str = ""
    agent_model_timeout_seconds: float = 60.0
    # 多副本部署必须用 postgres 共享草稿 loop 状态；memory 仅用于本地与单测。
    agent_checkpointer_backend: Literal["postgres", "memory"] = "postgres"
    payment_provider: Literal["mock", "alipay_sandbox", "alipay"] = "mock"
    alipay_app_id: str | None = None
    alipay_private_key: str | None = None
    alipay_public_key: str | None = None
    alipay_notify_url: str | None = None

    model_config = SettingsConfigDict(env_prefix="YITU_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免同一进程重复读取环境变量。"""
    return Settings()
