"""创建异常工单和履约冻结记录。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("courier_tasks", sa.Column("closed_reason", sa.Text(), nullable=True))
    op.add_column(
        "courier_tasks",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "courier_tasks",
        sa.Column("replaced_by_task_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_courier_tasks_replaced_by_task_id",
        "courier_tasks",
        "courier_tasks",
        ["replaced_by_task_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "sla_pauses",
        sa.Column("reason_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "sla_pauses",
        sa.Column("source_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "sla_pauses",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sla_pauses",
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sla_pauses",
        sa.Column("pause_idempotency_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "sla_pauses",
        sa.Column("resume_idempotency_key", sa.String(128), nullable=True),
    )
    op.create_foreign_key(
        "fk_sla_pauses_actor_id_users",
        "sla_pauses",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sla_pauses_source",
        "sla_pauses",
        ["source_type", "source_id"],
    )
    op.create_index(
        "ix_sla_pauses_pause_key",
        "sla_pauses",
        ["pause_idempotency_key"],
    )

    op.create_table(
        "exception_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_summary", postgresql.JSONB(), nullable=False),
        sa.Column("blocks_fulfillment", sa.Boolean(), nullable=False),
        sa.Column("frozen_shipment_status", sa.String(32), nullable=True),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "responsible_station_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("resolution_code", sa.String(64), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["responsible_station_id"],
            ["stations.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_exception_cases_source",
        ),
    )
    op.create_index(
        "ix_exception_cases_shipment_status",
        "exception_cases",
        ["shipment_id", "status"],
    )
    op.create_index(
        "ix_exception_cases_responsible_station_status",
        "exception_cases",
        ["responsible_station_id", "status"],
    )

    op.create_table(
        "shipment_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frozen_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("placed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("place_idempotency_key", sa.String(128), nullable=False),
        sa.Column("release_idempotency_key", sa.String(128), nullable=True),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["placed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_shipment_holds_source",
        ),
    )
    op.create_index(
        "ix_shipment_holds_shipment_active",
        "shipment_holds",
        ["shipment_id", "active"],
    )

    op.create_table(
        "exception_task_reassignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["exception_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["old_task_id"], ["courier_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_task_id"], ["courier_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "case_id",
            "old_task_id",
            "idempotency_key",
            name="uq_exception_task_reassignments_case_old_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("exception_task_reassignments")
    op.drop_index("ix_shipment_holds_shipment_active", table_name="shipment_holds")
    op.drop_table("shipment_holds")
    op.drop_index(
        "ix_exception_cases_responsible_station_status",
        table_name="exception_cases",
    )
    op.drop_index("ix_exception_cases_shipment_status", table_name="exception_cases")
    op.drop_table("exception_cases")
    op.drop_index("ix_sla_pauses_pause_key", table_name="sla_pauses")
    op.drop_index("ix_sla_pauses_source", table_name="sla_pauses")
    op.drop_constraint("fk_sla_pauses_actor_id_users", "sla_pauses", type_="foreignkey")
    op.drop_column("sla_pauses", "resume_idempotency_key")
    op.drop_column("sla_pauses", "pause_idempotency_key")
    op.drop_column("sla_pauses", "actor_id")
    op.drop_column("sla_pauses", "source_id")
    op.drop_column("sla_pauses", "source_type")
    op.drop_column("sla_pauses", "reason_code")
    op.drop_constraint(
        "fk_courier_tasks_replaced_by_task_id",
        "courier_tasks",
        type_="foreignkey",
    )
    op.drop_column("courier_tasks", "replaced_by_task_id")
    op.drop_column("courier_tasks", "closed_at")
    op.drop_column("courier_tasks", "closed_reason")
