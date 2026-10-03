from typing import Optional

from pydantic import BaseModel, ConfigDict


class RoomTypeResponse(BaseModel):
    id: int
    room_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
