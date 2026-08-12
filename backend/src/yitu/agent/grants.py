"""Agent 敏感动作授权的签发、校验和一次性消费。"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.drafts import DraftService
from yitu.agent.models import AgentActionGrant, AgentShipmentDraft
from yitu.identity.service import CurrentUser, require_resource_owner
from yitu.platform.audit import AuditService
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.platform.idempotency import canonical_json_sha256
from yitu.shipments.schemas import CreateShipmentCommand

CREATE_SHIPMENT = "CREATE_SHIPMENT"


class GrantView(BaseModel):
    """返回给客户端的授权摘要，不暴露完整业务快照。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    draft_revision: int
    quote_id: UUID
    quote_version: str
    expires_at: datetime
    consumed_at: datetime | None


class GrantService:
    """把明确确认转换为短时、一次性且不可跨版本复用的授权。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(self, conversation_id: UUID, actor: CurrentUser) -> GrantView:
        draft = await self._session.scalar(
            select(AgentShipmentDraft).where(
                AgentShipmentDraft.conversation_id == conversation_id,
                AgentShipmentDraft.owner_id == actor.id,
            )
        )
        if draft is None or draft.status != "READY_FOR_CONFIRMATION":
            raise AppError("AGENT_GRANT_NOT_READY", "草稿尚未完成校验和报价", 409)
        if draft.quote_id is None or draft.quote_version is None:
            raise AppError("AGENT_GRANT_QUOTE_REQUIRED", "授权缺少有效报价", 409)
        command = await DraftService(self._session).validate(conversation_id, actor)
        snapshot = command.model_dump(mode="json")
        grant = AgentActionGrant(
            conversation_id=conversation_id,
            owner_id=actor.id,
            action=CREATE_SHIPMENT,
            draft_id=draft.id,
            draft_revision=draft.revision,
            quote_id=draft.quote_id,
            quote_version=draft.quote_version,
            command_snapshot=snapshot,
            command_hash=canonical_json_sha256(snapshot),
            nonce=uuid4().hex,
            expires_at=Clock.now() + timedelta(minutes=5),
            created_at=Clock.now(),
        )
        self._session.add(grant)
        await self._session.flush()
        return GrantView.model_validate(grant)

    async def consume(self, grant_id: UUID, actor: CurrentUser, request_id: str) -> CreateShipmentCommand:
        """锁定授权并校验全部快照；调用方随后必须在同一事务创建运单。"""
        grant = await self._session.scalar(
            select(AgentActionGrant).where(AgentActionGrant.id == grant_id).with_for_update()
        )
        if grant is None:
            await self._reject(actor, f"agent-grant:{grant_id}", "AGENT_GRANT_NOT_FOUND", request_id)
            raise AppError("AGENT_GRANT_NOT_FOUND", "授权不存在", 404)
        now = Clock.now()
        try:
            if grant.owner_id != actor.id:
                raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能消费本人授权", 403)
            require_resource_owner(grant.owner_id, actor)
            if grant.action != CREATE_SHIPMENT:
                raise AppError("AGENT_GRANT_ACTION_INVALID", "授权动作不允许", 409)
            if grant.consumed_at is not None:
                raise AppError("AGENT_GRANT_CONSUMED", "授权已经消费", 409)
            if grant.expires_at <= now:
                raise AppError("AGENT_GRANT_EXPIRED", "授权已经过期", 409)
            draft = await self._session.get(AgentShipmentDraft, grant.draft_id, with_for_update=True)
            if draft is None or draft.revision != grant.draft_revision:
                raise AppError("AGENT_GRANT_DRAFT_CHANGED", "草稿已变化，请重新确认", 409)
            if draft.quote_id != grant.quote_id or draft.quote_version != grant.quote_version:
                raise AppError("AGENT_GRANT_QUOTE_CHANGED", "报价已变化，请重新确认", 409)
            command = CreateShipmentCommand.model_validate(grant.command_snapshot)
            if canonical_json_sha256(command.model_dump(mode="json")) != grant.command_hash:
                raise AppError("AGENT_GRANT_SNAPSHOT_INVALID", "授权快照校验失败", 409)
            grant.consumed_at = now
            await self._session.flush()
            return command
        except AppError as error:
            await self._reject(actor, f"agent-grant:{grant_id}", error.code, request_id)
            raise

    async def _reject(self, actor: CurrentUser, resource: str, code: str, request_id: str) -> None:
        await AuditService(self._session).record(
            actor=str(actor.id),
            action="agent.grant.rejected",
            resource=resource,
            before_summary=None,
            after_summary={"code": code},
            reason=code,
            request_id=request_id,
        )
        await self._session.flush()
