"""通知事实生成和渠道投递服务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.notifications.models import NotificationDelivery, NotificationMessage
from yitu.notifications.templates import render_template
from yitu.platform.clock import Clock, to_business_timezone


class NotificationService:
    """提供通知幂等生成和可重试的模拟投递。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        channels: tuple[str, ...] = ("IN_APP", "SMS"),
        clock: Clock | None = None,
    ) -> None:
        self.session = session
        self.channels = channels
        self.clock = clock or Clock()

    async def from_event(
        self,
        *,
        event_id: UUID,
        recipient_id: UUID,
        template_code: str,
        template_data: dict[str, object],
    ) -> NotificationMessage:
        """从业务事件生成通知及其渠道记录，重复调用保持幂等。"""
        message = await self.session.scalar(
            select(NotificationMessage).where(
                NotificationMessage.event_id == event_id,
                NotificationMessage.recipient_id == recipient_id,
            )
        )
        if message is None:
            rendered = render_template(template_code, template_data)
            message = NotificationMessage(
                event_id=event_id,
                recipient_id=recipient_id,
                template_code=template_code,
                template_data=template_data,
                title=rendered.title,
                content=rendered.content,
                status="UNREAD",
                created_at=to_business_timezone(self.clock.now()),
            )
            self.session.add(message)
            await self.session.flush()
        for channel in self.channels:
            delivery = await self.session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_id == event_id,
                    NotificationDelivery.recipient_id == recipient_id,
                    NotificationDelivery.channel == channel,
                )
            )
            if delivery is None:
                self.session.add(
                    NotificationDelivery(
                        message_id=message.id,
                        event_id=event_id,
                        recipient_id=recipient_id,
                        channel=channel,
                        status="PENDING",
                        created_at=to_business_timezone(self.clock.now()),
                    )
                )
        await self.session.flush()
        return message

    async def deliver_channel(
        self, delivery_id: UUID, *, simulate_failure: bool = False
    ) -> NotificationDelivery:
        """执行一次渠道投递；本阶段使用确定性的模拟渠道。"""
        delivery = await self.session.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise ValueError("通知投递记录不存在")
        if delivery.status == "DELIVERED":
            return delivery
        if delivery.status == "DEAD":
            raise ValueError("通知投递已进入死信状态")
        delivery.attempts += 1
        if simulate_failure:
            delivery.status = "DEAD" if delivery.attempts >= 5 else "FAILED"
            delivery.last_error = "模拟渠道投递失败"
        else:
            delivery.status = "DELIVERED"
            delivery.delivered_at = to_business_timezone(self.clock.now())
            delivery.last_error = None
        await self.session.flush()
        return delivery
