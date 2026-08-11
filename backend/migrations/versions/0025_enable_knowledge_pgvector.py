"""启用知识库 pgvector 向量列和检索索引。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QWEN_EMBEDDING_DIMENSION = 1024
LEGACY_EMBEDDING_CLEANUP_SQL = "DELETE FROM knowledge_chunks"


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    # 旧 JSONB 是 32 维测试向量，不能混入真实 Qwen 1024 维索引。
    op.execute(sa.text(LEGACY_EMBEDDING_CLEANUP_SQL))
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=postgresql.JSONB(),
        type_=Vector(QWEN_EMBEDDING_DIMENSION),
        postgresql_using="embedding::text::vector",
        existing_nullable=False,
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(128), nullable=False),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
    )
    op.create_check_constraint(
        "ck_knowledge_chunks_embedding_dimension",
        "knowledge_chunks",
        f"embedding_dimension = {QWEN_EMBEDDING_DIMENSION}",
    )
    op.create_check_constraint(
        "ck_knowledge_chunks_embedding_model",
        "knowledge_chunks",
        "length(embedding_model) > 0",
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_knowledge_chunks_content_fts "
            "ON knowledge_chunks USING gin (to_tsvector('simple', content))"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_chunks_content_fts",
        table_name="knowledge_chunks",
    )
    op.drop_index(
        "ix_knowledge_chunks_embedding_hnsw",
        table_name="knowledge_chunks",
    )
    op.drop_constraint(
        "ck_knowledge_chunks_embedding_model",
        "knowledge_chunks",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_chunks_embedding_dimension",
        "knowledge_chunks",
        type_="check",
    )
    op.drop_column("knowledge_chunks", "embedding_dimension")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(QWEN_EMBEDDING_DIMENSION),
        type_=postgresql.JSONB(),
        postgresql_using="embedding::text::jsonb",
        existing_nullable=False,
    )
