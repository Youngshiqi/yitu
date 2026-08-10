"""SLA 阶段实例的应用服务。"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.clock import Clock, to_business_timezone
from yitu.shipments.models import Shipment
from yitu.sla.calendar import add_work_hours, work_hours_between
from yitu.sla.models import SLAInstance, SLAPause, SLARule
from yitu.sla.policy import calculate_promised_at, rule_is_effective


def calculate_eta(instance: SLAInstance, expected_delay: timedelta = timedelta()) -> datetime | None:
    """基于冻结承诺时间投影 ETA，不修改承诺字段。"""
    if instance.promised_delivery_at is None:
        return None
    return instance.promised_delivery_at + expected_delay


class SLAService:
    """以事务内状态变更维护 SLA 生命周期。"""

    def __init__(self, session: AsyncSession, *, clock: Clock | None = None) -> None:
        self.session = session
        self.clock = clock or Clock()

    async def start(
        self, shipment_id: UUID, route_code: str, stage: str, *, service_type: str = "STANDARD"
    ) -> SLAInstance:
        """命中当前规则后创建阶段实例，并冻结承诺截止时间。"""
        now = to_business_timezone(self.clock.now())
        shipment = await self.session.get(Shipment, shipment_id)
        if shipment is None:
            raise ValueError("运单不存在")
        existing = await self.session.scalar(
            select(SLAInstance).where(SLAInstance.shipment_id == shipment_id, SLAInstance.stage == stage)
        )
        if existing is not None:
            return existing
        rules = (await self.session.scalars(
            select(SLARule).where(
                SLARule.route_code == route_code,
                SLARule.service_type == service_type,
                SLARule.stage == stage,
                SLARule.active.is_(True),
            ).order_by(SLARule.effective_from.desc())
        )).all()
        rule = next((item for item in rules if rule_is_effective(item, now)), None)
        if rule is None:
            raise ValueError("未找到生效的 SLA 规则")
        instance = SLAInstance(
            shipment_id=shipment.id,
            owner_id=shipment.owner_id,
            rule_id=rule.id,
            rule_version=rule.version,
            stage=stage,
            status="RUNNING",
            started_at=now,
            promised_delivery_at=calculate_promised_at(rule, now),
        )
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def pause(self, instance_id: UUID, reason: str) -> SLAInstance:
        """暂停运行中的 SLA，重复暂停保持幂等。"""
        instance = await self._get_instance(instance_id)
        if instance.status == "PAUSED":
            return instance
        if instance.status != "RUNNING":
            raise ValueError("当前 SLA 不可暂停")
        instance.status = "PAUSED"
        self.session.add(SLAPause(instance_id=instance.id, reason=reason, started_at=self.clock.now()))
        await self.session.flush()
        return instance

    async def resume(self, instance_id: UUID) -> SLAInstance:
        """恢复 SLA 并按暂停时间延后冻结的承诺截止时间。"""
        instance = await self._get_instance(instance_id)
        if instance.status == "RUNNING":
            return instance
        if instance.status != "PAUSED":
            raise ValueError("当前 SLA 不可恢复")
        pause = await self.session.scalar(
            select(SLAPause).where(SLAPause.instance_id == instance.id, SLAPause.ended_at.is_(None)).order_by(SLAPause.started_at.desc())
        )
        if pause is None:
            raise ValueError("未找到进行中的暂停记录")
        now = to_business_timezone(self.clock.now())
        started_at = to_business_timezone(pause.started_at)
        duration = now - started_at
        pause.ended_at = now
        pause.duration_seconds = int(duration.total_seconds())
        instance.paused_seconds += pause.duration_seconds
        rule = await self.session.get(SLARule, instance.rule_id)
        if rule is None or instance.promised_delivery_at is None:
            raise ValueError("SLA 实例数据不完整")
        if rule.target_work_hours is not None:
            worked = work_hours_between(started_at, now)
            instance.promised_delivery_at = add_work_hours(
                instance.promised_delivery_at, worked.total_seconds() / 3600
            )
        else:
            instance.promised_delivery_at += duration
        instance.status = "RUNNING"
        await self.session.flush()
        return instance

    async def complete(self, instance_id: UUID) -> SLAInstance:
        """完成 SLA 阶段并记录是否已经超过冻结承诺。"""
        instance = await self._get_instance(instance_id)
        if instance.status == "COMPLETED":
            return instance
        if instance.status != "RUNNING":
            raise ValueError("当前 SLA 不可完成")
        now = to_business_timezone(self.clock.now())
        instance.completed_at = now
        instance.status = "COMPLETED"
        instance.breached = instance.promised_delivery_at is not None and now > instance.promised_delivery_at
        await self.session.flush()
        return instance

    async def update_eta(self, instance_id: UUID, expected_delay: timedelta = timedelta()) -> SLAInstance:
        """更新预测到达时间，保留原始承诺时间不变。"""
        instance = await self._get_instance(instance_id)
        instance.eta_at = calculate_eta(instance, expected_delay)
        await self.session.flush()
        return instance

    async def scan_breaches(self, scan_key: str) -> list[SLAInstance]:
        """扫描超时运行实例；同一扫描窗口重复执行不会重复变更。"""
        now = to_business_timezone(self.clock.now())
        instances = (await self.session.scalars(
            select(SLAInstance).where(
                SLAInstance.status == "RUNNING",
                SLAInstance.promised_delivery_at < now,
            )
        )).all()
        changed: list[SLAInstance] = []
        for instance in instances:
            if instance.last_scan_key == scan_key:
                continue
            instance.breached = True
            instance.last_scan_key = scan_key
            changed.append(instance)
        await self.session.flush()
        return changed

    async def _get_instance(self, instance_id: UUID) -> SLAInstance:
        instance = await self.session.get(SLAInstance, instance_id)
        if instance is None:
            raise ValueError("SLA 实例不存在")
        return instance
