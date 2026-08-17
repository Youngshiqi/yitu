"""存量地址去重：按归一化五元组合并重复地址，重映射所有引用后删除冗余行。

分组键：(owner_id, trim(recipient_name), phone, district_region_id, trim(detail))
保留规则：优先正式条目（ephemeral=false），同级保留更早创建的（含 label 优先）。
引用重映射：
  - shipments.sender_address_id / receiver_address_id（硬 FK，RESTRICT）
  - agent_shipment_drafts.payload（JSONB 内的 sender/receiver_address_id）

用法：
    PYTHONPATH=src python scripts/dedupe_addresses.py --dry-run  # 只统计
    PYTHONPATH=src python scripts/dedupe_addresses.py --apply    # 实际执行
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select, update
from yitu.addresses.models import Address
from yitu.agent.models import AgentShipmentDraft
from yitu.identity.models import User  # noqa: F401 注册 mapper 依赖
from yitu.platform.database import SessionFactory, dispose_database
from yitu.pricing.models import QuoteSnapshot  # noqa: F401 注册 mapper 依赖
from yitu.regions.models import AdministrativeRegion  # noqa: F401 注册 mapper 依赖
from yitu.shipments.models import Shipment


def _group_key(row: Address) -> tuple:
    return (
        row.owner_id,
        row.recipient_name.strip(),
        row.phone.strip(),
        row.district_region_id,
        row.detail.strip(),
    )


def _canon_sort_key(row: Address) -> tuple:
    # 正式条目优先；有 label 优先；更早创建优先；id 兜底保证稳定
    return (row.ephemeral, row.label is None, row.id)


async def dedupe(dry_run: bool) -> None:
    async with SessionFactory() as session:
        rows = list(await session.scalars(select(Address).order_by(Address.id)))
        groups: dict[tuple, list[Address]] = defaultdict(list)
        for row in rows:
            groups[_group_key(row)].append(row)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
        redundant: dict[UUID, UUID] = {}  # 旧 id -> 保留 id
        for members in dup_groups.values():
            members.sort(key=_canon_sort_key)
            keep = members[0]
            for dup in members[1:]:
                redundant[dup.id] = keep.id
                # 保留条目缺失的信息从冗余条目回填
                if keep.label is None and dup.label is not None:
                    keep.label = dup.label
                if keep.ephemeral and not dup.ephemeral:
                    keep.ephemeral = False

        if not redundant:
            print(f"共 {len(rows)} 条地址，无重复。")
            return

        print(f"共 {len(rows)} 条地址，{len(dup_groups)} 组重复，将删除 {len(redundant)} 条冗余行。")
        if dry_run:
            for old, new in redundant.items():
                print(f"  {old} -> {new}")
            return

        # 1) shipments 硬 FK 重映射（RESTRICT，必须先于删除执行）
        for column in (Shipment.sender_address_id, Shipment.receiver_address_id):
            for old, new in redundant.items():
                await session.execute(
                    update(Shipment).where(column == old).values(**{column.key: new})
                )

        # 2) 草稿 payload（JSONB）内的地址 id 重映射：行数少，Python 层改写最稳
        for draft_row in await session.scalars(select(AgentShipmentDraft)):
            payload = dict(draft_row.payload)
            changed = False
            for column in ("sender_address_id", "receiver_address_id"):
                value = payload.get(column)
                if value is not None and UUID(str(value)) in redundant:
                    payload[column] = str(redundant[UUID(str(value))])
                    changed = True
            if changed:
                draft_row.payload = payload  # 整体赋值触发 JSONB 变更追踪

        # 3) 删除冗余行
        await session.execute(delete(Address).where(Address.id.in_(list(redundant))))

        await session.commit()
        print(f"已删除 {len(redundant)} 条冗余地址，引用已重映射。")


async def _main(dry_run: bool) -> None:
    try:
        await dedupe(dry_run=dry_run)
    finally:
        await dispose_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="地址簿存量去重")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只统计不修改")
    group.add_argument("--apply", action="store_true", help="执行去重")
    args = parser.parse_args()
    asyncio.run(_main(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
