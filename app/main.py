import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException

from app import db_models  # noqa: F401  rejestruje tabele w Base.metadata
from app.cache import JsonCache, make_redis
from app.database import Base, make_database
from app.models import ParkingLot, ParkingLotCreate, ParkingSpace, SpaceCreate, SpaceStatus, SpaceType, StatusUpdate
from app.repository import ParkingRepository


def get_repository(request: Request) -> ParkingRepository:
    return request.app.state.repository


def create_app(database_url=None, redis_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, sessions = make_database(
            database_url or os.getenv("DATABASE_URL", "sqlite:///./app.db")
        )
        client = None
        try:
            client = redis_client if redis_client is not None else make_redis(
                os.getenv("REDIS_URL", "redis://localhost:6379/0")
            )
            Base.metadata.create_all(engine)
            app.state.engine = engine
            app.state.redis = client
            app.state.repository = ParkingRepository(sessions)
            app.state.cache = JsonCache(
                client,
                prefix=os.environ["CACHE_PREFIX"],
                ttl=int(os.getenv("CACHE_TTL_SECONDS", "60")),
                resource_name="space",
            )
            app.state.repository.seed_if_empty()
            yield
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                engine.dispose()

    app = FastAPI(
        title="Parking Service",
        description="Student microservice for LAB2",
        version="0.2.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "parking-service"}

    @app.get("/parking-lots", response_model=list[ParkingLot])
    def list_lots(request: Request):
        return request.app.state.repository.list_lots()

    @app.post("/parking-lots", response_model=ParkingLot, status_code=201)
    def create_lot(data: ParkingLotCreate, request: Request):
        try:
            return request.app.state.repository.create_lot(data)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/parking-lots/{lot_id}", response_model=ParkingLot)
    def get_lot(lot_id: int, request: Request):
        try:
            return request.app.state.repository.get_lot(lot_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/parking-lots/{lot_id}/spaces", response_model=list[ParkingSpace])
    def list_spaces(
            lot_id: int,
            request: Request,
            status: SpaceStatus | None = None,
            type: SpaceType | None = None,
    ):
        try:
            return request.app.state.repository.list_spaces(lot_id, status, type)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/parking-lots/{lot_id}/spaces", response_model=ParkingSpace, status_code=201)
    def create_space(lot_id: int, data: SpaceCreate, request: Request):
        try:
            return request.app.state.repository.create_space(lot_id, data)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/spaces/{space_id}", response_model=ParkingSpace)
    def get_space(space_id: int, request: Request):
        try:
            return request.app.state.repository.get_space(space_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/spaces/{space_id}/status", response_model=ParkingSpace)
    def update_space_status(space_id: int, body: StatusUpdate, request: Request):
        try:
            return request.app.state.repository.update_status(space_id, body.status)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
