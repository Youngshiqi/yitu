from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yitu.platform.models import Base

if TYPE_CHECKING:
    from yitu.regions.models import AdministrativeRegion


class Address(Base):
    """保存客户地址簿中的收寄件地址。"""

    __tablename__ = "addresses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    province_region_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("administrative_regions.id", ondelete="RESTRICT"), nullable=True
    )
    city_region_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("administrative_regions.id", ondelete="RESTRICT"), nullable=True
    )
    district_region_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("administrative_regions.id", ondelete="RESTRICT"), nullable=True
    )
    district_code: Mapped[str] = mapped_column(String(12), nullable=False)
    detail: Mapped[str] = mapped_column(String(256), nullable=False)
    ephemeral: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    province_region: Mapped["AdministrativeRegion"] = relationship(
        foreign_keys=[province_region_id]
    )
    city_region: Mapped["AdministrativeRegion"] = relationship(
        foreign_keys=[city_region_id]
    )
    district_region: Mapped["AdministrativeRegion"] = relationship(
        foreign_keys=[district_region_id]
    )
