import itertools
import os
from contextlib import asynccontextmanager
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, HTTPException, Request
from py_eureka_client.eureka_client import EurekaClient
from pydantic import BaseModel, Field

PARKING_SERVICE = "PARKING-SERVICE"


class ReservationCreate(BaseModel):
    space_id: int
    user_id: str = Field(min_length=1, max_length=50)


class Reservation(ReservationCreate):
    id: int
    status: str = "ACTIVE"


def create_app(eureka_client: EurekaClient | None = None) -> FastAPI:
    # Klient tylko się tworzy; połączenie z Eureką nawiązuje dopiero start() w lifespan.
    client = eureka_client if eureka_client is not None else EurekaClient(
        eureka_server=os.getenv("EUREKA_SERVER_URL", "http://127.0.0.1:8761"),
        eureka_context="/eureka",
        app_name=os.getenv("SERVICE_NAME", "RESERVATION-SERVICE"),
        instance_ip=os.getenv("INSTANCE_IP", "127.0.0.1"),
        instance_host=os.getenv("INSTANCE_HOST", "localhost"),
        instance_port=int(os.getenv("SERVICE_PORT", "8102")),
        strict_service_error_policy=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # własne dane tej usługi; nie dotykają bazy Parking Service
        app.state.reservations = {}
        app.state.ids = itertools.count(1)
        app.state.eureka_client = client
        try:
            await client.start()
            yield
        finally:
            await client.stop()

    app = FastAPI(title="Reservation Service", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "reservation-service"}

    @app.post("/reservations", response_model=Reservation, status_code=201)
    async def create_reservation(data: ReservationCreate, request: Request):
        try:
            space = await request.app.state.eureka_client.do_service(
                PARKING_SERVICE,
                f"/spaces/{data.space_id}",
                return_type="json",
                timeout=2,
            )
        except HTTPError as exc:
            if exc.code == 404:
                raise HTTPException(status_code=404, detail="Space not found") from exc
            raise HTTPException(
                status_code=502, detail="Parking Service returned an HTTP error"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise HTTPException(
                status_code=503, detail="Parking Service is unavailable"
            ) from exc

        if space.get("status") != "FREE":
            raise HTTPException(status_code=409, detail="Space not available")

        reservation = Reservation(id=next(request.app.state.ids), **data.model_dump())
        request.app.state.reservations[reservation.id] = reservation
        return reservation

    @app.get("/reservations/{reservation_id}", response_model=Reservation)
    def get_reservation(reservation_id: int, request: Request):
        reservation = request.app.state.reservations.get(reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail=f"Reservation {reservation_id} not found")
        return reservation

    @app.get("/reservations", response_model=list[Reservation])
    def list_reservations(request: Request):
        return list(request.app.state.reservations.values())

    return app


app = create_app()
