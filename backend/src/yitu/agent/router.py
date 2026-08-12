"""Agent 会话、消息和 SSE API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.agent.drafts import DraftPatch, DraftService, DraftValidationView, DraftView
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
from yitu.agent.sse import agent_message_events, validate_agent_cursor
from yitu.identity.service import CurrentUser, get_current_user
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/agent/conversations", tags=["agent"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)
_model = Depends(get_model_adapter)
_last_event_id = Header(default=None, alias="Last-Event-ID")


@router.post("", response_model=ConversationView, status_code=201)
async def create_conversation(
    request: ConversationCreate,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> AgentConversation:
    """为当前用户创建一个可恢复会话。"""
    return await AgentConversationService(session).create(user, title=request.title)


@router.get("", response_model=list[ConversationView])
async def list_conversations(
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> list[AgentConversation]:
    """只列出当前用户自己的会话。"""
    return await AgentConversationService(session).list_conversations(user)


@router.get("/{conversation_id}", response_model=ConversationView)
async def get_conversation(
    conversation_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> AgentConversation:
    """读取当前用户拥有的会话摘要。"""
    return await AgentConversationService(session).get_owned(conversation_id, user)


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
async def list_messages(
    conversation_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> list[AgentMessage]:
    """按稳定顺序恢复当前用户的会话历史。"""
    return await AgentConversationService(session).list_messages(conversation_id, user)


@router.get("/{conversation_id}/draft", response_model=DraftView)
async def get_draft(
    conversation_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> DraftView:
    """恢复当前用户会话中的结构化运单草稿。"""
    await AgentConversationService(session).get_owned(conversation_id, user)
    draft = await DraftService(session).get_or_create(conversation_id, user)
    await session.commit()
    return DraftView.model_validate(draft)


@router.patch("/{conversation_id}/draft", response_model=DraftView)
async def update_draft(
    conversation_id: UUID,
    request: DraftPatch,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> DraftView:
    """合并结构化草稿字段，并立即失效旧报价。"""
    await AgentConversationService(session).get_owned(conversation_id, user)
    result = await DraftService(session).update(conversation_id, user, request)
    await session.commit()
    return result


@router.post("/{conversation_id}/draft/validate", response_model=DraftValidationView)
async def validate_draft(
    conversation_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
) -> DraftValidationView:
    """调用正式地址校验和计价服务，生成待确认数据。"""
    await AgentConversationService(session).get_owned(conversation_id, user)
    result = await DraftService(session).validate_and_quote(conversation_id, user)
    await session.commit()
    return result


@router.post("/{conversation_id}/messages", response_model=AgentTurnView)
async def send_message(
    conversation_id: UUID,
    request: MessageCreate,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
    model: ModelAdapter = _model,
) -> AgentTurnView:
    """保存用户消息，并通过可替换模型生成持久化回复。"""
    return await AgentConversationService(session).send_message(
        conversation_id,
        user,
        request.content,
        model,
    )


@router.get("/{conversation_id}/stream")
async def conversation_stream(
    conversation_id: UUID,
    user: CurrentUser = _current_user,
    session: AsyncSession = _session,
    last_event_id: UUID | None = _last_event_id,
) -> StreamingResponse:
    """返回有限消息批次和心跳，支持标准 Last-Event-ID 断线续传。"""
    await AgentConversationService(session).get_owned(conversation_id, user)
    await validate_agent_cursor(session, conversation_id, last_event_id)
    return StreamingResponse(
        agent_message_events(
            session,
            conversation_id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
