from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """汇总全部 SQLAlchemy 模型的共享元数据。"""

