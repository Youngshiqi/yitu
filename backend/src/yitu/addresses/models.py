from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from yitu.platform.models import Base


class Address(Base):
    """保存客户地址簿中的收寄件地址。"""

    __tablename__ = "addresses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    district_code: Mapped[str] = mapped_column(String(12), nullable=False)
    detail: Mapped[str] = mapped_column(String(256), nullable=False)
