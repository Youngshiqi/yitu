"""对话寄件使用的确定性业务操作。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.service import list_addresses
from yitu.agent.domain.drafts import DraftService
from yitu.agent.domain.grants import GrantService
from yitu.agent.domain.shipment_write_service import AgentWriteService
from yitu.agent.tools.drafts import execute_update_draft
from yitu.agent.workflow.state import (
    ConfirmationSnapshot,
    DraftProgress,
    QuoteProgress,
    ShipmentReceipt,
)
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError
from yitu.pricing.models import QuoteSnapshot


class ShipmentConversationService:
    """将草稿、报价、确认事实与建单服务收敛为节点可直接理解的操作。"""

    def __init__(self, session: AsyncSession, actor: CurrentUser) -> None:
        self._session = session
        self._actor = actor

    async def apply_user_message(
        self, conversation_id: UUID, actor_id: UUID, fields: dict[str, object]
    ) -> DraftProgress:
        """仅更新本轮明确字段并返回重新计算后的草稿进度。"""
        self._require_actor(actor_id)
        if fields:
            addresses = await list_addresses(self._session, self._actor)
            await execute_update_draft(
                self._session, self._actor, addresses, conversation_id, fields
            )
        return await self.load_progress(conversation_id, actor_id)

    async def load_progress(
        self, conversation_id: UUID, actor_id: UUID
    ) -> DraftProgress:
        self._require_actor(actor_id)
        draft_service = DraftService(self._session)
        draft = await draft_service.get_or_create(conversation_id, self._actor)
        view = await draft_service.view(draft, self._actor)
        return DraftProgress(
            status=view.status,
            revision=view.revision,
            missing_fields=view.missing_fields,
            snapshot={**view.payload, "summary": view.summary},
        )

    async def create_quote(
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
        )

    async def prepare_confirmation(
        self, conversation_id: UUID, actor_id: UUID
    ) -> ConfirmationSnapshot:
        self._require_actor(actor_id)
        drafts = DraftService(self._session)
        draft = await drafts.get_or_create(conversation_id, self._actor)
        if draft.status != "READY_FOR_CONFIRMATION" or draft.quote_id is None:
            raise AppError("AGENT_GRANT_NOT_READY", "草稿尚未完成校验和报价", 409)
        quote = await self._session.get(QuoteSnapshot, draft.quote_id)
        if quote is None or draft.quote_version is None:
            raise AppError("AGENT_QUOTE_MISSING", "报价快照不存在", 409)
        summary = await drafts.describe(draft, self._actor)
        return ConfirmationSnapshot(
            conversation_id=conversation_id,
            draft_revision=draft.revision,
            quote_id=draft.quote_id,
            quote_version=draft.quote_version,
            total_cents=quote.total_cents,
            summary="；".join(f"{item['label']}：{item['value']}" for item in summary),
        )

    async def create_confirmed_shipment(
        self, conversation_id: UUID, actor_id: UUID, request_id: str
    ) -> ShipmentReceipt:
        """建单前由既有 Grant/Write 服务再次校验版本、授权与幂等。"""
        self._require_actor(actor_id)
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
