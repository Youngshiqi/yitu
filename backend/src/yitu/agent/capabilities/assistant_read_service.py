"""主助手只读工具的显式白名单分发。"""

from uuid import UUID

from pydantic import BaseModel

from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.agent.tools.identity import AddressBookTool
from yitu.agent.tools.pricing import PricingRuleTool
from yitu.agent.tools.shipments import ShipmentReadInput, ShipmentReadTool
from yitu.agent.workflow.contracts import (
    AssistantToolCall,
    AssistantToolObservation,
)
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError


class AssistantReadService:
    def __init__(self, *, context: ToolContext, actor: CurrentUser) -> None:
        self._context = context
        self._actor = actor

    async def execute(
        self,
        call: AssistantToolCall,
        *,
        actor_id: UUID,
    ) -> AssistantToolObservation:
        self._require_actor(actor_id)
        result: ToolResult[BaseModel]
        if call.name == "get_own_shipment":
            result = await ShipmentReadTool().execute(
                ShipmentReadInput.model_validate(call.arguments), self._context
            )
        elif call.name == "list_addresses":
            result = await AddressBookTool().execute(self._context)
        elif call.name == "get_pricing_rules":
            result = await PricingRuleTool().execute(self._context)
        else:
            raise AppError("AGENT_TOOL_NOT_ALLOWED", "工具不在只读白名单中", 400)
        data = result.data
        return AssistantToolObservation(
            tool_call_id=call.id,
            name=call.name,
            found=result.found,
            content=result.message,
            data=data.model_dump(mode="json") if data is not None else None,
        )

    def _require_actor(self, actor_id: UUID) -> None:
        if actor_id != self._actor.id:
            raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能读取本人数据", 403)
