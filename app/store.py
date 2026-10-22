from app.models import ParkingLot, ParkingSpace, ParkingLotCreate, SpaceCreate, SpaceStatus


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
