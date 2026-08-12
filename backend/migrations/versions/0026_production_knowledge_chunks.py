"""补充生产知识块的章节、内容类型和索引版本元数据。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为已有向量块补齐可回溯元数据，再切换为非空约束。"""
    op.add_column(
        "knowledge_chunks",
        sa.Column("title", sa.String(512), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "section_path",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("content_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("chunking_version", sa.String(32), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE knowledge_chunks SET section_path = '[]'::jsonb, "
            "content_type = 'paragraph', chunking_version = 'legacy-v1', "
            "indexed_at = created_at WHERE section_path IS NULL"
        )
    )
    op.alter_column("knowledge_chunks", "section_path", nullable=False)
    op.alter_column("knowledge_chunks", "content_type", nullable=False)
    op.alter_column("knowledge_chunks", "chunking_version", nullable=False)
    op.alter_column("knowledge_chunks", "indexed_at", nullable=False)


def downgrade() -> None:
    """回退生产元数据列，保留原有向量和正文。"""
    op.drop_column("knowledge_chunks", "indexed_at")
    op.drop_column("knowledge_chunks", "chunking_version")
    op.drop_column("knowledge_chunks", "content_type")
    op.drop_column("knowledge_chunks", "section_path")
    op.drop_column("knowledge_chunks", "title")
