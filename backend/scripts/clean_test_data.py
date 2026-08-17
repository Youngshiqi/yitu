"""清理测试库业务脏数据。

保留：administrative_regions / alembic_version / checkpoint_migrations /
      knowledge_documents / knowledge_chunks / pricing_rules / service_areas /
      sla_rules / stations 以及 demo_key IS NOT NULL 的种子用户。
清空：30 张流水/运行态表 + demo_key IS NULL 的测试用户。

注意：users 不走 TRUNCATE CASCADE（会连带清空 knowledge_documents 等
FK 依赖表），改用精准 DELETE WHERE demo_key IS NULL，知识库等
RESTRICT FK 表不受影响。

用法:
    PYTHONPATH=src python scripts/clean_test_data.py --dry-run
    PYTHONPATH=src python scripts/clean_test_data.py --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text
from yitu.platform.database import SessionFactory, dispose_database

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

_DELETE_TEST_USERS = "DELETE FROM users WHERE demo_key IS NULL"


async def _count(session, table: str) -> int:
    return (await session.execute(text(f'SELECT COUNT(*) FROM "{table}"'))).scalar()


async def clean(dry_run: bool) -> None:
    async with SessionFactory() as session:
        # 统计清理前行数
        before_counts = {}
        for t in TRUNCATE_TABLES:
            before_counts[t] = await _count(session, t)
        total_users = await _count(session, "users")
        seed_count = (await session.execute(
            text("SELECT COUNT(*) FROM users WHERE demo_key IS NOT NULL")
        )).scalar()
        test_user_count = total_users - seed_count

        total_rows = sum(before_counts.values()) + test_user_count
        print("=" * 60)
        print(f"模式: {'DRY-RUN（不修改）' if dry_run else 'APPLY（执行清理）'}")
        print(f"将清空 {len(TRUNCATE_TABLES)} 张流水表（{sum(before_counts.values())} 行）")
        print(f"  + DELETE {test_user_count} 个测试用户（demo_key IS NULL）")
        print(f"  保留 {seed_count} 个种子用户 + {len(KEEP_TABLES)} 张配置/参考表")
        print("=" * 60)

        if dry_run:
            print("\n清空清单（按行数降序）：")
            all_items = sorted(before_counts.items(), key=lambda x: -x[1])
            for t, n in all_items:
                if n > 0:
                    print(f"  {t:35s} {n:>6} 行")
            print(f"  {'users (DELETE test)':35s} {test_user_count:>6} 行")
            print(f"\n种子用户（保留）：")
            rows = (await session.execute(text(
                "SELECT login_name, display_name, role, demo_key "
                "FROM users WHERE demo_key IS NOT NULL ORDER BY role"
            ))).fetchall()
            for r in rows:
                print(f"  {r[0]:30s} {r[1]:12s} {r[2]:20s} {r[3]}")
            print(f"\n保留的配置表：")
            for t in sorted(KEEP_TABLES):
                n = await _count(session, t)
                print(f"  {t:35s} {n:>6} 行")
            return

        # ---- APPLY ----
        # 1. TRUNCATE 流水表（不含 users，无 CASCADE 连带风险）
        table_list = ", ".join(f'"{t}"' for t in TRUNCATE_TABLES)
        await session.execute(text(
            f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"
        ))
        print(f"\n[1/3] 已 TRUNCATE {len(TRUNCATE_TABLES)} 张流水表")

        # 2. 精准删除测试用户（不影响 RESTRICT FK 表如 knowledge_documents）
        result = await session.execute(text(_DELETE_TEST_USERS))
        deleted = result.rowcount
        print(f"[2/3] 已 DELETE {deleted} 个测试用户")

        # 3. 提交
        await session.commit()
        print("[3/3] 已提交")

        # 验证
        print("\n清理后验证：")
        for t in TRUNCATE_TABLES:
            n = await _count(session, t)
            if n > 0:
                print(f"  ⚠️ {t:35s} {n:>6} 行（非预期残留）")
        remaining_users = await _count(session, "users")
        print(f"  {'users':35s} {remaining_users:>6} 行（种子用户）")
        for t in sorted(KEEP_TABLES):
            if t not in ("alembic_version",):
                n = await _count(session, t)
                print(f"  {t:35s} {n:>6} 行（保留）")
        print(f"\n✅ 清理完成。")

    await dispose_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="清理测试库业务脏数据")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只统计不修改")
    group.add_argument("--apply", action="store_true", help="执行清理")
    args = parser.parse_args()
    try:
        asyncio.run(clean(dry_run=args.dry_run))
    except Exception:
        asyncio.run(dispose_database())
        raise


if __name__ == "__main__":
    main()
