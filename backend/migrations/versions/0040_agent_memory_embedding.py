"""Agent 长期记忆增加语义向量列和 HNSW 索引。

存量记忆 embedding 为 NULL，召回时按 updated_at 兜底排序；
新记忆在写入时同步生成向量，失败降级为 NULL 不阻塞创建。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QWEN_EMBEDDING_DIMENSION = 1024


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.add_column(
        "agent_memories",
        sa.Column("embedding", Vector(QWEN_EMBEDDING_DIMENSION), nullable=True),
    )
    op.add_column(
        "agent_memories",
        sa.Column("embedding_model", sa.String(128), nullable=True),
    )
    op.create_check_constraint(
        "ck_agent_memories_embedding_model",
        "agent_memories",
        "embedding IS NULL OR (embedding_model IS NOT NULL AND length(embedding_model) > 0)",
    )
    op.create_index(
        "ix_agent_memories_embedding_hnsw",
        "agent_memories",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_agent_memories_embedding_hnsw", table_name="agent_memories")
    op.drop_constraint(
        "ck_agent_memories_embedding_model", "agent_memories", type_="check"
    )
    op.drop_column("agent_memories", "embedding_model")
    op.drop_column("agent_memories", "embedding")
