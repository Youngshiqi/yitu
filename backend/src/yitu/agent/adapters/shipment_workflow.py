"""把寄件工作流节点接到现有草稿、报价、授权和建单服务。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.service import list_addresses
from yitu.agent.drafts import DraftService
from yitu.agent.grants import GrantService
from yitu.agent.tools.drafts import execute_save_address, execute_update_draft
from yitu.agent.workflow_state.contracts import (
    ConfirmationSnapshot,
    DraftProgress,
    DraftToolCall,
    QuoteProgress,
    ShipmentReceipt,
)
from yitu.agent.write_tools import AgentWriteService
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError
from yitu.pricing.models import QuoteSnapshot


class ShipmentWorkflowAdapter:
    def __init__(
        self,
        *,
        session: AsyncSession,
        actor: CurrentUser,
    ) -> None:
        self._session = session
        self._actor = actor

    async def load_progress(
        self, conversation_id: UUID, actor_id: UUID
    ) -> DraftProgress:
        self._require_actor(actor_id)
        service = DraftService(self._session)
        draft = await service.get_or_create(conversation_id, self._actor)
        view = await service.view(draft, self._actor)
        return DraftProgress(
            status=view.status,
            revision=view.revision,
            missing_fields=view.missing_fields,
            snapshot={
                **view.payload,
                "summary": view.summary,
                "quote_id": str(view.quote_id) if view.quote_id else None,
                "quote_version": view.quote_version,
            },
        )

    async def execute_draft_tool(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        call: DraftToolCall,
    ) -> DraftProgress:
        self._require_actor(actor_id)
        if call.name == "update_draft":
            addresses = await list_addresses(self._session, self._actor)
            await execute_update_draft(
                self._session,
                self._actor,
                addresses,
                conversation_id,
                call.arguments,
            )
        elif call.name == "save_address":
            await execute_save_address(
                self._session,
                self._actor,
                conversation_id,
                call.arguments,
            )
        elif call.name != "inspect_draft":
            raise AppError("AGENT_TOOL_NOT_ALLOWED", "工具不在草稿白名单中", 400)
        return await self.load_progress(conversation_id, actor_id)

    async def validate_and_quote(
        self, conversation_id: UUID, actor_id: UUID
    ) -> QuoteProgress:
        self._require_actor(actor_id)
        result = await DraftService(self._session).validate_and_quote(
            conversation_id, self._actor
        )
        return QuoteProgress(
            quote_id=result.quote.id,
            quote_version=result.quote.rule_version,
            draft_revision=result.draft.revision,
            total_cents=result.quote.total_cents,
            expires_at=None,
        )

    async def prepare_confirmation(
        self, conversation_id: UUID, actor_id: UUID
    ) -> ConfirmationSnapshot:
        self._require_actor(actor_id)
        service = DraftService(self._session)
        draft = await service.get_or_create(conversation_id, self._actor)
        if draft.status != "READY_FOR_CONFIRMATION":
            raise AppError("AGENT_GRANT_NOT_READY", "草稿尚未完成校验和报价", 409)
        if draft.quote_id is None or draft.quote_version is None:
            raise AppError("AGENT_GRANT_QUOTE_REQUIRED", "确认缺少有效报价", 409)
        quote = await self._session.get(QuoteSnapshot, draft.quote_id)
        if quote is None:
            raise AppError("AGENT_QUOTE_MISSING", "报价快照不存在", 409)
        summary = await service.describe(draft, self._actor)
        return ConfirmationSnapshot(
            conversation_id=conversation_id,
            draft_revision=draft.revision,
            quote_id=draft.quote_id,
            quote_version=draft.quote_version,
            total_cents=quote.total_cents,
            summary="；".join(f"{item['label']}：{item['value']}" for item in summary),
        )

    async def create_confirmed(
        self,
        conversation_id: UUID,
        actor_id: UUID,
        request_id: str,
    ) -> ShipmentReceipt:
        self._require_actor(actor_id)
        # 授权签发与消费必须共享当前事务，模型无法直接调用任一步骤。
        grant = await GrantService(self._session).issue(conversation_id, self._actor)
        shipment = await AgentWriteService(self._session).create_shipment(
            grant.id, self._actor, request_id
        )
        quote = await self._session.get(QuoteSnapshot, grant.quote_id)
        if quote is None:
            raise AppError("AGENT_QUOTE_MISSING", "报价快照不存在", 409)
        return ShipmentReceipt(
            shipment_id=shipment.id,
            shipment_no=shipment.shipment_no,
            total_cents=quote.total_cents,
        )

    def _require_actor(self, actor_id: UUID) -> None:
        if actor_id != self._actor.id:
            raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能操作本人寄件草稿", 403)
