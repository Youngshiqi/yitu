"""创建运单聚合表。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_no", sa.String(32), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("receiver_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_station_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_station_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pickup_method", sa.String(32), nullable=False),
        sa.Column("delivery_method", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sender_address_id"], ["addresses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receiver_address_id"], ["addresses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["origin_station_id"], ["stations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_station_id"], ["stations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("shipment_no", name="uq_shipments_shipment_no"),
    )


def downgrade() -> None:
    op.drop_table("shipments")
