from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yitu.identity.models import Station
from yitu.platform.models import Base


class ServiceArea(Base):
    """保存区县到网点和服务类型的确定性映射。"""

    __tablename__ = "service_areas"
    __table_args__ = (
        UniqueConstraint(
            "district_code", "service_type", name="uq_service_areas_lookup"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    district_code: Mapped[str] = mapped_column(String(12), nullable=False)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    station_id: Mapped[UUID] = mapped_column(
        ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    station: Mapped[Station] = relationship()
