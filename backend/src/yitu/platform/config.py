from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中读取应用运行所需的环境配置。"""

    app_name: str = "Yitu Logistics API"
    business_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    database_url: str = (
        "postgresql+asyncpg://yitu:yitu_test@127.0.0.1:55432/yitu_test"
    )

    model_config = SettingsConfigDict(env_prefix="YITU_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免同一进程重复读取环境变量。"""
    return Settings()
