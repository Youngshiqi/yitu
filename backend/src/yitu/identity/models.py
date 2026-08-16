import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yitu.platform.clock import Clock
from yitu.platform.models import Base


class Role(str, enum.Enum):
    """阶段二使用的五种业务角色。"""

    CUSTOMER = "CUSTOMER"
    COURIER = "COURIER"
    STATION_OPERATOR = "STATION_OPERATOR"
    OPERATIONS_ADMIN = "OPERATIONS_ADMIN"


class Station(Base):
    """保存网点标识和服务区域基础字段。"""

    __tablename__ = "stations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    district_code: Mapped[str] = mapped_column(String(12), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=Clock.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=Clock.now, onupdate=Clock.now
    )

    users: Mapped[list["User"]] = relationship(back_populates="station")


class User(Base):
    """保存登录身份、业务角色和可选网点范围。"""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("login_name", name="uq_users_login_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    login_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[Role] = mapped_column(String(32), nullable=False)
    station_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=True
    )
    demo_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    station: Mapped[Station | None] = relationship(back_populates="users")
