from datetime import datetime, timezone
from app.models import SessionCreate, ParkingSession

class SessionStore:
    def __init__(self):
        self.sessions: dict[int, ParkingSession] = {}
        self.next_id: int = 0

    def add(self, session_create: SessionCreate) -> ParkingSession:
        session_id = self.next_id

        session = ParkingSession(id=session_id, space_id=session_create.space_id, vehicle_plate=session_create.vehicle_plate, started_at=datetime.now(timezone.utc))
        
        self.sessions[session_id] = session
        self.next_id += 1

        return session