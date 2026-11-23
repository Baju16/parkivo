from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class PaymentRow(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
