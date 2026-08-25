"""可跨节点、子图和 checkpoint 传递的稳定数据契约。"""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

_TRUSTED_ARGUMENT_NAMES = {
    "actor_id",
    "conversation_id",
    "grant_id",
    "request_id",
    "user_id",
}


class StrictContract(BaseModel):
    """跨边界 DTO 默认拒绝未声明字段，避免无意扩大信任范围。"""

    model_config = ConfigDict(extra="forbid")


class WorkflowError(StrictContract):
    code: str
    message: str
    source_node: str
    retryable: bool = False


class ShipmentReceipt(StrictContract):
    shipment_id: UUID
    shipment_no: str
    total_cents: int = Field(ge=0)


class KnowledgeSearchInput(StrictContract):
    query: str = Field(min_length=1, max_length=1000)
    category: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=5, ge=1, le=5)


class KnowledgeCitation(StrictContract):
    document_id: UUID
    filename: str
    index_version: int
    title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    content: str
    score: float


class KnowledgeEvidence(StrictContract):
    found: bool
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    message: str


class AssistantToolCall(StrictContract):
    id: str
    name: Literal[
        "search_knowledge",
        "get_own_shipment",
        "list_addresses",
        "get_current_identity",
        "get_pricing_rules",
    ]
    arguments: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_trusted_arguments(self) -> Self:
        forbidden = sorted(_TRUSTED_ARGUMENT_NAMES.intersection(self.arguments))
        if forbidden:
            raise ValueError("模型工具参数不得包含：" + "、".join(forbidden))
        return self


class AssistantToolObservation(StrictContract):
    tool_call_id: str
    name: str
    found: bool
    content: str
    data: dict[str, object] | None = None


class DraftToolCall(StrictContract):
    id: str
    name: Literal["inspect_draft", "update_draft", "save_address"]
    arguments: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_trusted_arguments(self) -> Self:
        forbidden = sorted(_TRUSTED_ARGUMENT_NAMES.intersection(self.arguments))
        if forbidden:
            raise ValueError("模型工具参数不得包含：" + "、".join(forbidden))
        return self


class DraftProgress(StrictContract):
    status: str
    revision: int = Field(ge=0)
    missing_fields: list[str] = Field(default_factory=list)
    snapshot: dict[str, object] = Field(default_factory=dict)


class QuoteProgress(StrictContract):
    quote_id: UUID
    quote_version: str
    draft_revision: int = Field(ge=0)
    total_cents: int = Field(ge=0)
    expires_at: str | None = None


class ConfirmationSnapshot(StrictContract):
    conversation_id: UUID
    draft_revision: int = Field(ge=0)
    quote_id: UUID
    quote_version: str
    total_cents: int = Field(ge=0)
    summary: str
