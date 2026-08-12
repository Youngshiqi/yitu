"""Agent 工具共享上下文和结果契约。"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.identity.service import CurrentUser

ResultT_co = TypeVar("ResultT_co", bound=BaseModel, covariant=True)


@dataclass(frozen=True, slots=True)
class ToolContext:
    """从已验证 JWT 和请求会话构造的可信工具上下文。"""

    actor: CurrentUser
    session: AsyncSession


class ToolResult(BaseModel, Generic[ResultT_co]):
    """所有只读工具统一返回的结构化信封。"""

    model_config = ConfigDict(extra="forbid")

    tool: str
    found: bool
    data: ResultT_co | None
    message: str
