"""创建客户地址簿。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table("addresses", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("label", sa.String(32), nullable=True), sa.Column("recipient_name", sa.String(128), nullable=False), sa.Column("phone", sa.String(32), nullable=False), sa.Column("district_code", sa.String(12), nullable=False), sa.Column("detail", sa.String(256), nullable=False), sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"))

def downgrade() -> None:
    op.drop_table("addresses")
