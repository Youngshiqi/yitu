"""内部工作流事件到稳定公开事件的唯一映射。"""

from dataclasses import dataclass
from typing import TypeAlias

PublicAgentEvent: TypeAlias = tuple[str, dict[str, object]]


@dataclass(frozen=True, slots=True)
class UserMessageStored:
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class TokenGenerated:
    content: str


@dataclass(frozen=True, slots=True)
class AssistantMessageStored:
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class WorkflowFailed:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class NodeCompleted:
    node: str


InternalAgentEvent: TypeAlias = (
    UserMessageStored
    | TokenGenerated
    | AssistantMessageStored
    | WorkflowFailed
    | NodeCompleted
)


class AgentEventMapper:
    """只允许前端契约中的四类生命周期事件穿过边界。"""

    def map(self, event: InternalAgentEvent) -> PublicAgentEvent | None:
        if isinstance(event, UserMessageStored):
            return "user_message", event.payload
        if isinstance(event, TokenGenerated):
            return "delta", {"content": event.content}
        if isinstance(event, AssistantMessageStored):
            return "done", event.payload
        if isinstance(event, WorkflowFailed):
            return "error", {"code": event.code, "message": event.message}
        return None
