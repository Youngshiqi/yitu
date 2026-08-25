"""Agent 请求追踪：为 API、图路由和工具结果提供可关联的 trace_id。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from yitu.platform.clock import Clock


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """单个 Agent 执行事件；payload 只允许结构化摘要，不保存密钥和完整提示词。"""

    trace_id: UUID
    event: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


class AgentTrace:
    """单次 Agent 执行的有界事件收集器。"""

    def __init__(self, trace_id: UUID | None = None, max_events: int = 64) -> None:
        self.trace_id = trace_id or uuid4()
        self._max_events = max_events
        self.events: list[TraceEvent] = []

    def record(self, event: str, **payload: Any) -> TraceEvent:
        """追加事件并限制事件数量，防止异常循环造成无限增长。"""
        item = TraceEvent(self.trace_id, event, Clock.now(), payload)
        if len(self.events) < self._max_events:
            self.events.append(item)
        return item

    def summary(self) -> dict[str, Any]:
        """返回可写入消息信封或日志的最小追踪摘要。"""
        return {
            "trace_id": str(self.trace_id),
            "events": [
                {
                    "event": item.event,
                    "created_at": item.created_at.isoformat(),
                    **item.payload,
                }
                for item in self.events
            ],
        }
