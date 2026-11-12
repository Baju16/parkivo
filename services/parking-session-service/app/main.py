import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.models import SessionCreate, ParkingSession
from app.database import Base, make_database
from app.repository import ParkingSessionsRepository

def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = database_url or os.getenv("DATABASE_URL", "sqlite:///./sessions.db")
        engine, sessions = make_database(url)

        try:
            Base.metadata.create_all(engine)
            app.state.repository = ParkingSessionsRepository(sessions)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Parking Session Service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "parking-session-service"}


    @app.post("/sessions", response_model=ParkingSession, status_code=201)
    def create_session(payload: SessionCreate):
        try:
            return app.state.repository.add(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    

    @app.get("/sessions", response_model=list[ParkingSession])
    def list_session():
        return app.state.repository.list_session()


    @app.get("/sessions/{session_id}", response_model=ParkingSession)
    def get_session(session_id: int):
        try:
            return app.state.repository.get_by_id(session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


    @app.post("/sessions/{session_id}/end", response_model=ParkingSession)
    def end_session(session_id: int):
        try:
            return app.state.repository.end_session(session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        
    return app

app = create_app()