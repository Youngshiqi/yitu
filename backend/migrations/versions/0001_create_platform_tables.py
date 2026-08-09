"""建立平台数据库迁移基线并启用 pgvector。"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """启用后续知识库模型需要的 vector 扩展。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """移除当前基线拥有的 vector 扩展。"""
    op.execute("DROP EXTENSION IF EXISTS vector")
