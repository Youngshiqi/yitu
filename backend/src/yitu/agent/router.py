"""Agent 会话、记忆、草稿、授权和 SSE API。"""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.drafts import DraftPatch, DraftService, DraftValidationView, DraftView
from yitu.agent.grants import GrantService, GrantView
from yitu.agent.memory import MemoryCreate, MemoryService, MemoryView
from yitu.agent.model_adapter import ModelAdapter, get_model_adapter
from yitu.agent.models import AgentConversation, AgentMessage
from yitu.agent.schemas import (
    AgentTurnView,
    ConversationCreate,
    ConversationView,
    MessageCreate,
    MessageView,
)
from yitu.agent.service import AgentConversationService
from yitu.agent.sse import (
    agent_message_events,
    encode_agent_event,
    validate_agent_cursor,
)
from yitu.agent.write_tools import AgentWriteService
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session
from yitu.shipments.service import ShipmentView

router = APIRouter(prefix="/api/v1/agent/conversations", tags=["agent"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)
_model = Depends(get_model_adapter)
_last_event_id = Header(default=None, alias="Last-Event-ID")


@router.post("", response_model=ConversationView, status_code=201)
async def create_conversation(request: ConversationCreate, user: CurrentUser = _current_user, session: AsyncSession = _session) -> AgentConversation:
    """为当前用户创建可恢复会话。"""
    return await AgentConversationService(session).create(user, title=request.title)


@router.get("", response_model=list[ConversationView])
async def list_conversations(user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[AgentConversation]:
    """列出当前用户会话。"""
    return await AgentConversationService(session).list_conversations(user)


# 固定路径必须声明在 /{conversation_id} 前，避免被动态 UUID 路由吞掉。
@router.get("/memories", response_model=list[MemoryView])
async def list_memories(user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[MemoryView]:
    """列出当前用户有效的持久记忆。"""
    return await MemoryService(session).list(user)


@router.post("/memories", response_model=MemoryView, status_code=201)
async def create_memory(body: MemoryCreate, user: CurrentUser = _current_user, session: AsyncSession = _session) -> MemoryView:
    """用户明确确认后创建持久记忆。"""
    result = await MemoryService(session).create(body, user)
    await session.commit()
    return result


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> None:
    """停用当前用户的一条持久记忆。"""
    await MemoryService(session).delete(memory_id, user)
    await session.commit()


@router.post("/grants/{grant_id}/consume", response_model=ShipmentView, status_code=201)
async def consume_grant(grant_id: UUID, request: Request, user: CurrentUser = _current_user, session: AsyncSession = _session) -> ShipmentView:
    """原子消费授权并调用共享运单创建服务。"""
    result = await AgentWriteService(session).create_shipment(grant_id, user, request.state.request_id)
    await session.commit()
    return result


@router.get("/{conversation_id}", response_model=ConversationView)
async def get_conversation(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> AgentConversation:
    """读取当前用户拥有的会话。"""
    return await AgentConversationService(session).get_owned(conversation_id, user)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, request: Request, user: CurrentUser = _current_user, session: AsyncSession = _session) -> None:
    """删除会话正文和关联数据，仅保留匿名审计摘要。"""
    await AgentConversationService(session).delete_conversation(conversation_id, user, request.state.request_id)
    await session.commit()


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
async def list_messages(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> list[AgentMessage]:
    """按稳定顺序恢复当前用户的会话消息。"""
    return await AgentConversationService(session).list_messages(conversation_id, user)


@router.get("/{conversation_id}/draft", response_model=DraftView)
async def get_draft(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> DraftView:
    await AgentConversationService(session).get_owned(conversation_id, user)
    draft = await DraftService(session).get_or_create(conversation_id, user)
    await session.commit()
    return DraftView.model_validate(draft)


@router.patch("/{conversation_id}/draft", response_model=DraftView)
async def update_draft(conversation_id: UUID, request: DraftPatch, user: CurrentUser = _current_user, session: AsyncSession = _session) -> DraftView:
    await AgentConversationService(session).get_owned(conversation_id, user)
    result = await DraftService(session).update(conversation_id, user, request)
    await session.commit()
    return result


@router.post("/{conversation_id}/draft/validate", response_model=DraftValidationView)
async def validate_draft(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> DraftValidationView:
    await AgentConversationService(session).get_owned(conversation_id, user)
    result = await DraftService(session).validate_and_quote(conversation_id, user)
    await session.commit()
    return result


@router.post("/{conversation_id}/grant", response_model=GrantView, status_code=201)
async def issue_grant(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session) -> GrantView:
    await AgentConversationService(session).get_owned(conversation_id, user)
    result = await GrantService(session).issue(conversation_id, user)
    await session.commit()
    return result


@router.post("/{conversation_id}/messages", response_model=AgentTurnView)
async def send_message(conversation_id: UUID, request: MessageCreate, user: CurrentUser = _current_user, session: AsyncSession = _session, model: ModelAdapter = _model) -> AgentTurnView:
    return await AgentConversationService(session).send_message(conversation_id, user, request.content, model)


@router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: UUID,
    request: MessageCreate,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
    model: ModelAdapter = _model,
) -> StreamingResponse:
    """通过单个鉴权请求实时返回用户消息确认和助手增量文本。"""
    service = AgentConversationService(session)
    await service.get_owned(conversation_id, user)

    async def events() -> AsyncIterator[str]:
        async for event, payload in service.stream_message(
            conversation_id, user, request.content, model
        ):
            yield encode_agent_event(event, payload)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{conversation_id}/stream")
async def conversation_stream(conversation_id: UUID, user: CurrentUser = _current_user, session: AsyncSession = _session, last_event_id: UUID | None = _last_event_id) -> StreamingResponse:
    await AgentConversationService(session).get_owned(conversation_id, user)
    await validate_agent_cursor(session, conversation_id, last_event_id)
    return StreamingResponse(agent_message_events(session, conversation_id, last_event_id=last_event_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
