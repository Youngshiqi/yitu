"""持久化 MinerU 解析任务和产物追踪信息。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("mineru_task_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("source_artifact_key", sa.String(512), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("markdown_artifact_key", sa.String(512), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("result_archive_key", sa.String(512), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("parse_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("parse_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    # MinerU 任务 ID 是 Worker 重启后恢复轮询的稳定标识，不允许关联多个文档。
    op.create_index(
        "ix_knowledge_documents_mineru_task_id",
        "knowledge_documents",
        ["mineru_task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_documents_mineru_task_id",
        table_name="knowledge_documents",
    )
    for name in (
        "parse_finished_at",
        "parse_started_at",
        "result_archive_key",
        "markdown_artifact_key",
        "source_artifact_key",
        "mineru_task_id",
    ):
        op.drop_column("knowledge_documents", name)
