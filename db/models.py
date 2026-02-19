from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String, default="")
    password: Mapped[str] = mapped_column(String, default="")
    min_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class OrderLog(Base):
    __tablename__ = "order_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_slug: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
