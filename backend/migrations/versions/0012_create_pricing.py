"""创建版本化价格规则和报价快照表。"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("route_code", sa.String(32), nullable=False),
        sa.Column("base_fee_cents", sa.Integer(), nullable=False),
        sa.Column("additional_fee_cents", sa.Integer(), nullable=False),
        sa.Column("remote_surcharge_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("version", "route_code", name="uq_pricing_rules_version_route"),
    )
    op.create_table(
        "quote_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("fee_items", postgresql.JSONB(), nullable=False),
        sa.Column("volume_weight_grams", sa.Integer(), nullable=False),
        sa.Column("billable_weight_grams", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rule_id"], ["pricing_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_quote_id"], ["quote_snapshots.id"], ondelete="RESTRICT"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO pricing_rules (id, version, route_code, base_fee_cents, additional_fee_cents, remote_surcharge_cents, effective_from)
            VALUES
              ('40000000-0000-4000-8000-000000000001', 'pricing-demo-v1', 'SAME_CITY', 800, 200, 0, CURRENT_TIMESTAMP),
              ('40000000-0000-4000-8000-000000000002', 'pricing-demo-v1', 'BJ_SH', 1500, 600, 0, CURRENT_TIMESTAMP),
              ('40000000-0000-4000-8000-000000000003', 'pricing-demo-v1', 'CROSS_REGION', 1200, 500, 0, CURRENT_TIMESTAMP)
            """
        )
    )
def downgrade() -> None:
    op.drop_table("quote_snapshots")
    op.drop_table("pricing_rules")
