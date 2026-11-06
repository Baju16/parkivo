from fastapi import FastAPI, HTTPException
from threading import Lock
from datetime import datetime, timezone

from app.models import SessionCreate, ParkingSession
from app.store import  SessionStore

def create_app() -> FastAPI:
    app = FastAPI(title="Parking Session Service")
    store = SessionStore()
    lock = Lock()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "parking-session-service"}


    @app.post("/sessions", response_model=ParkingSession, status_code=201)
    def create_session(payload: SessionCreate):
        with lock:
            for session in store.sessions.values():
                if (session.space_id == payload.space_id and session.ended_at is None):
                    raise HTTPException(status_code=409, detail="Miejsce ma juz aktywną sesję")
            
            return store.add(payload)


    @app.get("/sessions", response_model=list[ParkingSession])
    def list_session():
        with lock:
            return list(store.sessions.values())


    @app.get("/sessions/{session_id}", response_model=ParkingSession)
    def get_session(session_id: int):
        with lock:
            session = store.sessions.get(session_id)
            
            if session is None:
                raise HTTPException(status_code=404, detail="Sesja nie istnieje")
            
            return session


    @app.post("/sessions/{session_id}/end", response_model=ParkingSession)
    def end_session(session_id: int):
        with lock:
            session = store.sessions.get(session_id)

            if session is None:
                raise HTTPException(status_code=404, detail="Sesja nie istnieje")
            
            if session.ended_at is not None:
                raise HTTPException(status_code=409, detail="Sesja jest juz zakończona")
            
            session.ended_at = datetime.now(timezone.utc)

            return session
        
    return app

app = create_app()