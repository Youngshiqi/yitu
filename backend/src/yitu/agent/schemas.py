"""Agent 会话和消息 API 契约。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """创建会话时允许提供的可选标题。"""

    title: str | None = Field(default=None, min_length=1, max_length=128)


class ConversationView(BaseModel):
    """用户可见的会话摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    """提交给 Agent 的单条用户消息。"""

    content: str = Field(min_length=1, max_length=8000)


class MessageView(BaseModel):
    """持久化消息的公开字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    envelope: dict[str, object] | None
    created_at: datetime


class AgentTurnView(BaseModel):
    """一次用户输入及对应模型回复。"""

    user_message: MessageView
    assistant_message: MessageView
