from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class SessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    space_id: int = Field(gt=0)
    vehicle_plate: str = Field(min_length=1)

class ParkingSession(SessionCreate):
    id: int 
    started_at: datetime
    ended_at: datetime | None = None