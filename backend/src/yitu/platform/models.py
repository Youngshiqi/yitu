import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """汇总全部 SQLAlchemy 模型的共享元数据。"""


outbox_events = sa.Table(
    "outbox_events",
    Base.metadata,
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column("event_type", sa.String(128), nullable=False),
    sa.Column("business_id", sa.String(128), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("idempotency_key", sa.String(128), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_error", sa.Text(), nullable=True),
)
