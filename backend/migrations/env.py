from asyncio import run
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from yitu.addresses import models as _address_models  # noqa: F401
from yitu.dispatch import models as _dispatch_models  # noqa: F401
from yitu.identity import models as _identity_models  # noqa: F401
from yitu.payments import models as _payment_models  # noqa: F401
from yitu.platform.config import get_settings
from yitu.platform.models import Base
from yitu.pricing import models as _pricing_models  # noqa: F401
from yitu.shipments import credential_models as _credential_models  # noqa: F401
from yitu.shipments import models as _shipment_models  # noqa: F401
from yitu.shipments import transport_models as _transport_models  # noqa: F401
from yitu.stations import models as _station_models  # noqa: F401
from yitu.tracking import models as _tracking_models  # noqa: F401

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None and config.get_section("loggers") is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在不建立数据库连接时生成迁移 SQL。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在同步迁移上下文中执行版本脚本。"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """通过异步 PostgreSQL 驱动建立迁移连接。"""
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "server_settings": {"timezone": settings.business_timezone},
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run(run_async_migrations())
