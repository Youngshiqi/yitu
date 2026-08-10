"""创建运单轨迹事件表。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracking_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("message", sa.String(256), nullable=False),
        sa.Column("visible_to_customer", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("shipment_id", "idempotency_key", name="uq_tracking_events_idempotency"),
        sa.UniqueConstraint("shipment_id", "sequence_no", name="uq_tracking_events_sequence"),
    )


def downgrade() -> None:
    op.drop_table("tracking_events")
