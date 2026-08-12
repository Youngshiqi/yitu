import enum
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yitu.knowledge.embedding import QWEN_EMBEDDING_DIMENSION
from yitu.platform.models import Base


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PARSE_FAILED = "PARSE_FAILED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
    DEACTIVATED = "DEACTIVATED"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("sha256", name="uq_knowledge_documents_sha256"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(String(32), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parse_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mineru_task_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    source_artifact_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    markdown_artifact_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_archive_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parse_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parse_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "index_version",
            "chunk_index",
            name="uq_knowledge_chunks_position",
        ),
        CheckConstraint(
            f"embedding_dimension = {QWEN_EMBEDDING_DIMENSION}",
            name="ck_knowledge_chunks_embedding_dimension",
        ),
        CheckConstraint(
            "length(embedding_model) > 0",
            name="ck_knowledge_chunks_embedding_model",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(QWEN_EMBEDDING_DIMENSION),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    section_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(32), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "ix_knowledge_chunks_embedding_hnsw",
    KnowledgeChunk.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
Index(
    "ix_knowledge_chunks_content_fts",
    # REGCONFIG 必须作为 SQL 字面量编译，否则建表元数据会生成不可执行的绑定参数。
    func.to_tsvector(text("'simple'"), KnowledgeChunk.content),
    postgresql_using="gin",
)
