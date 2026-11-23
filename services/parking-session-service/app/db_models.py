from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ParkingSessionRow(Base):
    __tablename__ = "parking_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    space_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_plate: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_paid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )


    __table_args__ = (
        CheckConstraint("space_id > 0", name="positive_space_id"),
        Index(
            "one_active_session_per_space",
            "space_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL")
        )
    )


class ProcessedEventRow(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
