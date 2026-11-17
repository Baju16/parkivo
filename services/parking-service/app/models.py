from pydantic import BaseModel, Field
from enum import Enum

class SpaceStatus(str, Enum):
    FREE = "FREE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"

class SpaceType(str, Enum):
    STANDARD = "STANDARD"
    DISABLED = "DISABLED"
    EV = "EV"  #ELECTRIC VEHICLE

class ParkingLotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

class ParkingLot(ParkingLotCreate):
    id: int

class SpaceCreate(BaseModel):
    number: str = Field(min_length=1, max_length=10) #np.A-12
    type: SpaceType = SpaceType.STANDARD

class ParkingSpace(SpaceCreate):
    id: int
    parking_lot_id: int
    status: SpaceStatus = SpaceStatus.FREE

class StatusUpdate(BaseModel):
    status: SpaceStatus
