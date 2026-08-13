import enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yitu.platform.models import Base


class RegionLevel(str, enum.Enum):
    """客户端地址选择使用的三级行政区划。"""

    PROVINCE = "PROVINCE"
    CITY = "CITY"
    DISTRICT = "DISTRICT"


class AdministrativeRegion(Base):
    """保存固定版本的行政区划节点及其父子关系。"""

    __tablename__ = "administrative_regions"
    __table_args__ = (
        UniqueConstraint("level", "code", name="uq_regions_level_code"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[RegionLevel] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("administrative_regions.id", ondelete="RESTRICT"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_version: Mapped[str] = mapped_column(String(32), nullable=False)

    parent: Mapped["AdministrativeRegion | None"] = relationship(
        remote_side="AdministrativeRegion.id"
    )
