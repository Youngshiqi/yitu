"""为运单增加单包裹申报和报价绑定。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipment_packages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_weight_grams", sa.Integer(), nullable=False),
        sa.Column("estimated_length_cm", sa.Integer(), nullable=False),
        sa.Column("estimated_width_cm", sa.Integer(), nullable=False),
        sa.Column("estimated_height_cm", sa.Integer(), nullable=False),
        sa.Column("declared_value_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("special_instructions", sa.Text(), nullable=True),
        sa.Column("actual_weight_grams", sa.Integer(), nullable=True),
        sa.Column("actual_length_cm", sa.Integer(), nullable=True),
        sa.Column("actual_width_cm", sa.Integer(), nullable=True),
        sa.Column("actual_height_cm", sa.Integer(), nullable=True),
        sa.Column("reweighed_by", sa.UUID(), nullable=True),
        sa.Column("reweighed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reweighed_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.add_column("shipments", sa.Column("quote_id", sa.UUID(), nullable=True))
    op.add_column("shipments", sa.Column("package_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_shipments_quote_id", "shipments", "quote_snapshots", ["quote_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_shipments_package_id", "shipments", "shipment_packages", ["package_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_shipments_package", "shipments", ["package_id"])


def downgrade() -> None:
    op.drop_constraint("uq_shipments_package", "shipments", type_="unique")
    op.drop_constraint("fk_shipments_package_id", "shipments", type_="foreignkey")
    op.drop_constraint("fk_shipments_quote_id", "shipments", type_="foreignkey")
    op.drop_column("shipments", "package_id")
    op.drop_column("shipments", "quote_id")
    op.drop_table("shipment_packages")
