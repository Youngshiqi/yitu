"""Agent 受控写工具：只有已消费授权才能创建正式运单。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.grants import GrantService
from yitu.identity.service import CurrentUser
from yitu.shipments.service import ShipmentApplicationService, ShipmentView


class AgentWriteService:
    """把授权消费和共享运单应用服务放在同一数据库事务中。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_shipment(
        self, grant_id: UUID, actor: CurrentUser, request_id: str
    ) -> ShipmentView:
        command = await GrantService(self._session).consume(grant_id, actor, request_id)
        return await ShipmentApplicationService(self._session).create(
            command,
            actor,
            idempotency_key=f"agent-grant:{grant_id}",
        )
