from fastapi import FastAPI, Request, Depends, HTTPException

from app.models import ParkingLot, ParkingLotCreate, ParkingSpace, SpaceCreate, SpaceStatus, SpaceType, StatusUpdate
from app.store import Store, seed


ALLOWED_TRANSITIONS = {
    SpaceStatus.FREE: {SpaceStatus.RESERVED, SpaceStatus.OCCUPIED, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.RESERVED: {SpaceStatus.FREE, SpaceStatus.OCCUPIED, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.OCCUPIED: {SpaceStatus.FREE, SpaceStatus.OUT_OF_SERVICE},
    SpaceStatus.OUT_OF_SERVICE: {SpaceStatus.FREE},
}


def get_store(request: Request) -> Store:
    return request.app.state.store


def create_app() -> FastAPI:
    app = FastAPI(
        title="Parking Service",
        description="Student microservice for LAB1",
        version="0.1.0",
    )
    # Każda instancja aplikacji ma własny magazyn w pamięci.
    store = Store()
    seed(store)
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "parking-service"}

    # TODO: dodaj tutaj modele/endpointy własnej domeny lub dołącz routery.
    @app.get("/parking-lots", response_model=list[ParkingLot])
    def list_lots(store: Store = Depends(get_store)):
        return list(store.lots.values())

    @app.post("/parking-lots", response_model=ParkingLot, status_code=201)
    def create_lot(data: ParkingLotCreate, store: Store = Depends(get_store)):
        if store.lot_name_exists(data.name):
            raise HTTPException(
                status_code=409,
                detail=f"Parking lot with name '{data.name}' already exists",
            )
        return store.add_lot(data)

    @app.get("/parking-lots/{lot_id}", response_model=ParkingLot)
    def get_lot(lot_id: int, store: Store = Depends(get_store)):
        lot = store.get_lot(lot_id)
        if lot is None:
            raise HTTPException(status_code=404, detail=f"Parking lot {lot_id} not found")
        return lot

    @app.get("/parking-lots/{lot_id}/spaces", response_model=list[ParkingSpace])
    def list_spaces(
            lot_id: int,
            status: SpaceStatus | None = None,
            type: SpaceType | None = None,
            store: Store = Depends(get_store)
    ):
        lot = store.get_lot(lot_id)
        if lot is None:
            raise HTTPException(status_code=404,detail=f"Parking lot {lot_id} not found")
        return store.list_spaces(lot_id, status, type)

    @app.post("/parking-lots/{lot_id}/spaces", response_model=ParkingSpace, status_code=201)
    def create_space(lot_id: int, data: SpaceCreate, store: Store = Depends(get_store)):
        lot = store.get_lot(lot_id)
        if lot is None:
            raise HTTPException(status_code=404, detail=f"Parking lot {lot_id} not found")
        if store.space_number_exists(lot_id, data.number):
            raise HTTPException(
                status_code=409,
                detail=f"Space {data.number} already exists in parking lot {lot_id}",
            )
        return store.add_space(lot_id, data)

    @app.get("/spaces/{space_id}", response_model=ParkingSpace)
    def get_space(space_id: int, store: Store = Depends(get_store)):
        space = store.get_space(space_id)
        if space is None:
            raise HTTPException(status_code=404,detail=f"Space {space_id} not found")
        return space

    @app.patch("/spaces/{space_id}/status", response_model=ParkingSpace)
    def update_space_status(space_id: int, body: StatusUpdate, store: Store = Depends(get_store)):
        space = store.get_space(space_id)
        if space is None:
            raise HTTPException(status_code=404, detail=f"Space {space_id} not found")
        if body.status not in ALLOWED_TRANSITIONS[space.status]:
            raise HTTPException(
                status_code=409,
                detail=f"Niedozwolona zmiana statusu: {space.status.value} -> {body.status.value}",
            )
        space.status = body.status
        return space

    # Magazyn twórz tylko raz na aplikację; endpointy korzystają z app.state.

    return app


app = create_app()


# TODO:
# 1. Choose your domain and name the service.
# 2. Add your domain models.
# 3. Add one list endpoint and one detail endpoint.
# 4. Add one create or update endpoint.
# 5. Add a business rule beyond types, required fields and unique identifiers.
# 6. Reject invalid operations before changing state; handle 404, 409 and 422.
# 7. Add at least three domain tests with fresh application state for each test.
# 8. Verify write/read and restart via HTTP; complete the README.
