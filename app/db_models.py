from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ParkingLotRow(Base):
    __tablename__ = "parking_lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(String(200))


class ParkingSpaceRow(Base):
    __tablename__ = "parking_spaces"
    __table_args__ = (UniqueConstraint("parking_lot_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    number: Mapped[str] = mapped_column(String(10))
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
