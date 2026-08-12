"""为中文混合检索增加 jieba 分词字段和全文索引。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保留旧块并用原文临时回填，新建索引版本时会写入正式 jieba 词元。"""
    op.add_column(
        "knowledge_chunks",
        sa.Column("search_tokens", sa.Text(), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("tokenizer_version", sa.String(32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE knowledge_chunks SET search_tokens = content, "
            "tokenizer_version = 'legacy-unsegmented' "
            "WHERE search_tokens IS NULL"
        )
    )
    op.alter_column("knowledge_chunks", "search_tokens", nullable=False)
    op.alter_column("knowledge_chunks", "tokenizer_version", nullable=False)
    op.drop_index(
        "ix_knowledge_chunks_content_fts",
        table_name="knowledge_chunks",
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_knowledge_chunks_content_fts "
            "ON knowledge_chunks USING gin "
            "(to_tsvector('simple', search_tokens))"
        )
    )


def downgrade() -> None:
    """恢复基于原始正文的全文索引。"""
    op.drop_index(
        "ix_knowledge_chunks_content_fts",
        table_name="knowledge_chunks",
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_knowledge_chunks_content_fts "
            "ON knowledge_chunks USING gin (to_tsvector('simple', content))"
        )
    )
    op.drop_column("knowledge_chunks", "tokenizer_version")
    op.drop_column("knowledge_chunks", "search_tokens")
