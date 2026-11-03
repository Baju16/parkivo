from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db_models import ParkingLotRow, ParkingSpaceRow
from app.models import ParkingLotCreate, SpaceCreate, SpaceStatus, SpaceType

ALLOWED_TRANSITIONS = {
    SpaceStatus.FREE: {SpaceStatus.RESERVED, SpaceStatus.OCCUPIED, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.RESERVED: {SpaceStatus.FREE, SpaceStatus.OCCUPIED, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.OCCUPIED: {SpaceStatus.FREE, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.OUT_OF_SERVICE: {SpaceStatus.FREE},
}


def lot_payload(row: ParkingLotRow) -> dict:
    return {"id": row.id, "name": row.name, "address": row.address}


def space_payload(row: ParkingSpaceRow) -> dict:
    return {
        "id": row.id,
        "parking_lot_id": row.parking_lot_id,
        "number": row.number,
        "type": row.type,
        "status": row.status,
    }


class ParkingRepository:
    """Każda operacja ma własną sesję; zmiana kończy się commitem albo rollbackiem."""

    def __init__(self, sessions):
        self.sessions = sessions

    def list_lots(self) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(ParkingLotRow).order_by(ParkingLotRow.id))
            return [lot_payload(r) for r in rows]

    def get_lot(self, lot_id: int) -> dict:
        with self.sessions() as db:
            row = db.get(ParkingLotRow, lot_id)
            if row is None:
                raise LookupError(f"Parking lot {lot_id} not found")
            return lot_payload(row)

    def create_lot(self, data: ParkingLotCreate) -> dict:
        try:
            with self.sessions.begin() as db:
                exists = db.scalar(
                    select(ParkingLotRow.id).where(ParkingLotRow.name == data.name)
                )
                if exists is not None:
                    raise ValueError(
                        f"Parking lot with name '{data.name}' already exists"
                    )
                row = ParkingLotRow(name=data.name, address=data.address)
                db.add(row)
                db.flush()
                return lot_payload(row)
        except IntegrityError as exc:
            raise ValueError(
                f"Parking lot with name '{data.name}' already exists"
            ) from exc

    def list_spaces(
        self,
        lot_id: int,
        status: SpaceStatus | None = None,
        type: SpaceType | None = None,
    ) -> list[dict]:
        with self.sessions() as db:
            if db.get(ParkingLotRow, lot_id) is None:
                raise LookupError(f"Parking lot {lot_id} not found")
            query = select(ParkingSpaceRow).where(ParkingSpaceRow.parking_lot_id == lot_id)
            if status is not None:
                query = query.where(ParkingSpaceRow.status == status.value)
            if type is not None:
                query = query.where(ParkingSpaceRow.type == type.value)
            rows = db.scalars(query.order_by(ParkingSpaceRow.id))
            return [space_payload(r) for r in rows]

    def get_space(self, space_id: int) -> dict:
        with self.sessions() as db:
            row = db.get(ParkingSpaceRow, space_id)
            if row is None:
                raise LookupError(f"Space {space_id} not found")
            return space_payload(row)

    def create_space(self, lot_id: int, data: SpaceCreate) -> dict:
        message = f"Space {data.number} already exists in parking lot {lot_id}"
        try:
            with self.sessions.begin() as db:
                if db.get(ParkingLotRow, lot_id) is None:
                    raise LookupError(f"Parking lot {lot_id} not found")
                exists = db.scalar(
                    select(ParkingSpaceRow.id).where(
                        ParkingSpaceRow.parking_lot_id == lot_id,
                        ParkingSpaceRow.number == data.number,
                    )
                )
                if exists is not None:
                    raise ValueError(message)
                row = ParkingSpaceRow(
                    parking_lot_id=lot_id,
                    number=data.number,
                    type=data.type.value,
                    status=SpaceStatus.FREE.value,
                )
                db.add(row)
                db.flush()
                return space_payload(row)
        except IntegrityError as exc:
            raise ValueError(message) from exc

    def update_status(self, space_id: int, new_status: SpaceStatus) -> dict:
        # odczyt stanu -> sprawdzenie reguły -> zmiana -> commit
        with self.sessions.begin() as db:
            row = db.get(ParkingSpaceRow, space_id)
            if row is None:
                raise LookupError(f"Space {space_id} not found")
            current = SpaceStatus(row.status)
            if new_status not in ALLOWED_TRANSITIONS[current]:
                raise ValueError(
                    f"Niedozwolona zmiana statusu: {current.value} -> {new_status.value}"
                )
            row.status = new_status.value
            db.flush()
            return space_payload(row)

    def seed_if_empty(self) -> None:
        """Dane początkowe tylko do pustej bazy — restart nie nadpisuje zmian."""
        with self.sessions() as db:
            if db.scalar(select(ParkingLotRow.id).limit(1)) is not None:
                return
        lot = self.create_lot(
            ParkingLotCreate(name="Parking Szpital", address="ul. lwowska 60")
        )
        self.create_space(lot["id"], SpaceCreate(number="A-01"))
        self.create_space(lot["id"], SpaceCreate(number="A-02", type=SpaceType.EV))
        self.create_space(lot["id"], SpaceCreate(number="A-03", type=SpaceType.DISABLED))
