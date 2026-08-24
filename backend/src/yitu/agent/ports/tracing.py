"""节点可观测事件端口。"""

from typing import Protocol


class TracePort(Protocol):
    def record(self, event: str, **payload: object) -> None: ...

    def summary(self) -> dict[str, object]: ...
