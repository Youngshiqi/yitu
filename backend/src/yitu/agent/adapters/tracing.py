"""现有有界追踪器到节点 TracePort 的适配。"""

from yitu.agent.tracing import AgentTrace


class AgentTraceAdapter:
    def __init__(self, trace: AgentTrace) -> None:
        self._trace = trace

    def record(self, event: str, **payload: object) -> None:
        self._trace.record(event, **payload)

    def summary(self) -> dict[str, object]:
        return self._trace.summary()
