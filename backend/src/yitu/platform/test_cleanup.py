"""测试库业务脏数据清理（供 pytest teardown 与 scripts/clean_test_data.py 复用）。

保留：administrative_regions / alembic_version / checkpoint_migrations /
      knowledge_documents / knowledge_chunks / pricing_rules / service_areas /
      sla_rules / stations 以及 demo_key IS NOT NULL 的种子用户。
清空：流水/运行态表 + demo_key IS NULL 的测试用户。

注意：users 不走 TRUNCATE CASCADE（会连带清空 knowledge_documents 等
FK 依赖表），改用精准 DELETE WHERE demo_key IS NULL，知识库等
RESTRICT FK 表不受影响。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# 保留的配置/参考表（不清空）
KEEP_TABLES: frozenset[str] = frozenset({
    "administrative_regions",
    "alembic_version",
    "checkpoint_migrations",  # langgraph schema 版本追踪
    "knowledge_documents",   # FK RESTRICT → users，必须保护
    "knowledge_chunks",      # FK CASCADE → knowledge_documents
    "pricing_rules",
    "service_areas",
    "sla_rules",
    "stations",
})

# 清空的流水/运行态表（不含 users，users 用精准 DELETE）
TRUNCATE_TABLES: tuple[str, ...] = (
    "addresses",
    "agent_action_grants",
    "agent_conversations",
    "agent_memories",
    "agent_messages",
    "agent_shipment_drafts",
    "audit_entries",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoints",
    "courier_tasks",
    "dead_letters",
    "exception_cases",
    "exception_task_reassignments",
    "idempotency_records",
    "notification_deliveries",
    "notification_messages",
    "outbox_events",
    "payment_transactions",
    "pickup_credentials",
    "proofs_of_delivery",
    "quote_snapshots",
    "recovery_cases",
    "shipment_holds",
    "shipment_packages",
    "shipments",
    "sla_instances",
    "sla_pauses",
    "tracking_events",
    "transport_legs",
)

_DELETE_TEST_USERS = "DELETE FROM users WHERE demo_key IS NULL AND phone IS NULL"


async def clean_business_data(session: AsyncSession) -> int:
    """清空业务脏数据并提交，返回删除的测试用户数。

    调用方需提供已开启的 session；本函数负责 TRUNCATE、DELETE 与提交。
    """
    table_list = ", ".join(f'"{t}"' for t in TRUNCATE_TABLES)
    await session.execute(text(
        f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"
    ))
    result = await session.execute(text(_DELETE_TEST_USERS))
    deleted = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return deleted


async def clean_test_database(database_url: str) -> int:
    """用独立 engine 执行清理后立即释放，供 pytest 会话结束时调用。

    测试文件可能用 function 级 event loop 复用并 dispose 过模块级 engine；
    此处新建 engine 全程在当前 loop 内使用，避免跨 loop 复用连接触发
    「Future attached to a different loop」。
    """
    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            return await clean_business_data(session)
    finally:
        await engine.dispose()
