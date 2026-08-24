"""Agent 会话 CRUD 与 LangGraph Runtime 兼容门面。"""

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import assign_region_path, find_matching_address
from yitu.agent.checkpoint_store import delete_thread
from yitu.agent.drafts import DraftPatch, DraftService, DraftView
from yitu.agent.models import AgentActionGrant, AgentConversation, AgentMessage
from yitu.agent.runtime import AgentRuntime, AgentRuntimeContext, PublicAgentEvent
from yitu.agent.schemas import AgentTurnView, DraftAddressCreate
from yitu.identity.service import CurrentUser
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.pricing.models import QuoteSnapshot
from yitu.shipments.service import ShipmentView


class AgentConversationService:
    """只维护兼容 API；模型、工具和流程控制全部属于 AgentRuntime。"""

    def __init__(self, session: AsyncSession, runtime: AgentRuntime | None = None) -> None:
        self._session = session
        self._runtime = runtime

    async def create(self, actor: CurrentUser, *, title: str | None = None) -> AgentConversation:
        now = Clock.now()
        row = AgentConversation(owner_id=actor.id, title=title, status="ACTIVE", created_at=now, updated_at=now)
        self._session.add(row)
        await self._session.commit()
        return row

    async def list_conversations(self, actor: CurrentUser) -> list[AgentConversation]:
        rows = await self._session.scalars(
            select(AgentConversation)
            .where(AgentConversation.owner_id == actor.id, exists().where(AgentMessage.conversation_id == AgentConversation.id))
            .order_by(AgentConversation.updated_at.desc(), AgentConversation.id)
        )
        return list(rows.all())

    async def get_owned(self, conversation_id: UUID, actor: CurrentUser) -> AgentConversation:
        row = await self._session.get(AgentConversation, conversation_id)
        if row is None or row.owner_id != actor.id:
            raise AppError("AGENT_CONVERSATION_NOT_FOUND", "Agent 会话不存在", 404)
        return row

    async def list_messages(self, conversation_id: UUID, actor: CurrentUser) -> list[AgentMessage]:
        await self.get_owned(conversation_id, actor)
        rows = await self._session.scalars(
            select(AgentMessage).where(AgentMessage.conversation_id == conversation_id).order_by(AgentMessage.created_at, AgentMessage.id)
        )
        return list(rows.all())

    async def send_message(self, conversation_id: UUID, content: str, context: AgentRuntimeContext) -> AgentTurnView:
        return await self._require_runtime().invoke_message(conversation_id, content, context)

    def stream_message(self, conversation_id: UUID, content: str, context: AgentRuntimeContext) -> AsyncIterator[PublicAgentEvent]:
        return self._require_runtime().stream_message(conversation_id, content, context)

    async def save_draft_address(self, conversation_id: UUID, actor: CurrentUser, payload: DraftAddressCreate) -> DraftView:
        await self.get_owned(conversation_id, actor)
        address = await find_matching_address(
            self._session, actor.id, payload.recipient_name, payload.phone,
            payload.district_region_id, payload.detail,
        )
        if address is not None:
            if payload.save and address.ephemeral:
                address.ephemeral = False
                address.label = address.label or payload.label
        else:
            address = Address(
                owner_id=actor.id, label=payload.label if payload.save else None,
                recipient_name=payload.recipient_name, phone=payload.phone,
                detail=payload.detail, ephemeral=not payload.save,
            )
            await assign_region_path(
                self._session, address, payload.province_region_id,
                payload.city_region_id, payload.district_region_id,
            )
            self._session.add(address)
            await self._session.flush()
        return await DraftService(self._session).update(
            conversation_id, actor,
            DraftPatch(
                sender_address_id=address.id if payload.role == "sender" else None,
                receiver_address_id=address.id if payload.role == "receiver" else None,
                origin_district_code=address.district_code if payload.role == "sender" else None,
                destination_district_code=address.district_code if payload.role == "receiver" else None,
            ),
        )

    async def record_consumption_receipt(self, grant_id: UUID, actor: CurrentUser, shipment: ShipmentView) -> None:
        grant = await self._session.get(AgentActionGrant, grant_id)
        if grant is None or grant.owner_id != actor.id:
            return
        quote = await self._session.get(QuoteSnapshot, grant.quote_id)
        if quote is None:
            return
        now = Clock.now()
        self._session.add_all([
            AgentMessage(conversation_id=grant.conversation_id, role="user", content="确认", envelope=None, created_at=now),
            AgentMessage(
                conversation_id=grant.conversation_id, role="assistant",
                content=f"运单 {shipment.shipment_no} 已创建，待支付 {quote.total_cents / 100:.2f} 元。",
                envelope={"action": "SHIPMENT_CREATED", "grant_id": str(grant_id)},
                created_at=now + timedelta(milliseconds=1),
            ),
        ])

    async def delete_conversation(self, conversation_id: UUID, actor: CurrentUser, request_id: str) -> None:
        row = await self.get_owned(conversation_id, actor)
        await AuditService(self._session).record(
            actor=str(actor.id), action="agent.conversation.deleted",
            resource="agent-conversation:anonymous",
            before_summary={"conversation_id": str(row.id)}, after_summary={"deleted": True},
            reason="user_requested", request_id=request_id,
        )
        await self._session.delete(row)
        await self._session.flush()
        await delete_thread(conversation_id)

    def _require_runtime(self) -> AgentRuntime:
        if self._runtime is None:
            raise RuntimeError("AgentRuntime 未注入")
        return self._runtime
