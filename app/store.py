from app.models import ParkingLot, ParkingSpace, ParkingLotCreate, SpaceCreate, SpaceStatus, SpaceType

class Store:
    def __init__(self):
        self.lots: dict[int, ParkingLot] = {}
        self.spaces: dict[int, ParkingSpace] = {}
        self.next_lot_id = 1
        self.next_space_id = 1

    def add_lot(self, data: ParkingLotCreate) -> ParkingLot:
        lot = ParkingLot(id=self.next_lot_id, **data.model_dump())
        self.lots[lot.id] = lot
        self.next_lot_id += 1
        return lot

    def add_space(self, lot_id: int, data: SpaceCreate) -> ParkingSpace:
        space = ParkingSpace(
            id=self.next_space_id,
            parking_lot_id=lot_id,
            status=SpaceStatus.FREE,
            **data.model_dump(),
        )
        self.spaces[space.id] = space
        self.next_space_id += 1
        return space

    def get_lot(self, lot_id: int) -> ParkingLot | None:
        return self.lots.get(lot_id)

    def get_space(self, space_id: int) -> ParkingSpace | None:
        return self.spaces.get(space_id)

    def lot_name_exists(self, name: str) -> bool:
        return any(lot.name == name for lot in self.lots.values())

    def space_number_exists(self, lot_id: int, number: str) -> bool:
        return any(
            s.parking_lot_id == lot_id and s.number == number
            for s in self.spaces.values()
        )

    def list_spaces(
        self,
        lot_id: int,
        status: SpaceStatus | None = None,
        type: SpaceType | None = None,
    ) -> list[ParkingSpace]:
        spaces = [s for s in self.spaces.values() if s.parking_lot_id == lot_id]
        if status is not None:
            spaces = [s for s in spaces if s.status == status]
        if type is not None:
            spaces = [s for s in spaces if s.type == type]
        return spaces

def seed(store: Store) -> None:
    lot = store.add_lot(
        ParkingLotCreate(name="Parking Szpital", address="ul. lwowska 60")
    )
    store.add_space(lot.id, SpaceCreate(number="A-01"))
    store.add_space(lot.id, SpaceCreate(number="A-02", type=SpaceType.EV))
    store.add_space(lot.id, SpaceCreate(number="A-03", type=SpaceType.DISABLED))