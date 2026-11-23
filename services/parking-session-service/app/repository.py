from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.db_models import ParkingSessionRow, ProcessedEventRow
from app.models import SessionCreate

def session_payload(row: ParkingSessionRow) -> dict:
    ended_at = row.ended_at
    if ended_at is not None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)

    return {
        "id": row.id,
        "space_id": row.space_id,
        "vehicle_plate": row.vehicle_plate,
        "started_at": row.started_at.replace(tzinfo=timezone.utc),
        "ended_at": ended_at,
        "is_paid": row.is_paid
    }

class ParkingSessionsRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def get_by_id(self, session_id: int) -> dict:
        with self.sessions() as db:
            row = db.get(ParkingSessionRow, session_id)
            if row is None:
                raise LookupError("Sesja nie istnieje")
            
            return session_payload(row)
        
    def list_session(self) -> list[dict]:
        with self.sessions() as db:
            query = select(ParkingSessionRow).order_by(ParkingSessionRow.id)
            rows = db.scalars(query)
            return [session_payload(row) for row in rows]
        
    def add(self, data: SessionCreate) -> dict:
        try:
            with self.sessions.begin() as db:
                next_id = select(func.coalesce(func.max(ParkingSessionRow.id) + 1, 0)).scalar_subquery()

                row = ParkingSessionRow(
                    id=next_id,
                    space_id=data.space_id,
                    vehicle_plate=data.vehicle_plate,
                    started_at=datetime.now(timezone.utc),
                    ended_at=None,
                )

                db.add(row)
                db.flush()

                return session_payload(row)
            
        except IntegrityError as exc:
            if str(exc.orig) == "UNIQUE constraint failed: parking_sessions.space_id":
                raise ValueError("Miejsce ma juz aktywną sesję") from exc
            raise

    def end_session(self, session_id: int) -> dict:
        with self.sessions.begin() as db:
            statement = update(ParkingSessionRow).where(ParkingSessionRow.id == session_id, ParkingSessionRow.ended_at.is_(None)).values(ended_at=datetime.now(timezone.utc))
            result = db.execute(statement)

            row = db.get(ParkingSessionRow, session_id)
            if row is None:
                raise LookupError("Sesja nie istnieje")

            if result.rowcount == 0:
                raise ValueError("Sesja jest juz zakończona")

            return session_payload(row)
        
    def apply_payment_event(self, event_id: str, session_id: int) -> bool:
        try:
            with self.sessions.begin() as db:
                if db.get(ProcessedEventRow, event_id) is not None:
                    return False

                db.add(ProcessedEventRow(event_id=event_id))
                db.flush()

                row = db.get(ParkingSessionRow, session_id)
                if row is None:
                    raise LookupError("Sesja nie istnieje")

                if row.ended_at is None:
                    raise ValueError("Sesja nadal trwa")

                row.is_paid = True

            return True

        except IntegrityError:
            with self.sessions() as db:
                if db.get(ProcessedEventRow, event_id) is not None:
                    return False
            raise

