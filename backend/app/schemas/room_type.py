from typing import Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict


class RoomTypeResponse(BaseModel):
    id: int
    name: Optional[str] = None
    code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Alias for Reference
RoomTypeReference = RoomTypeResponse


class RoomType(str, Enum):
    """Phân loại phòng trọ cơ bản."""
    ROOM = "ROOM"                          # Phòng trọ truyền thống
    STUDIO = "STUDIO"                      # Căn hộ mini, studio
    APARTMENT = "APARTMENT"                # Căn hộ chung cư, chung cư dịch vụ
    SLEEPBOX = "SLEEPBOX"                  # Ký túc xá, sleepbox, giường tầng
    WHOLE_HOUSE = "WHOLE_HOUSE"            # Nhà nguyên căn


ROOM_TYPE_CODE_TO_ID: dict[str, int] = {
    RoomType.ROOM.value: 1,
    RoomType.STUDIO.value: 2,
    RoomType.APARTMENT.value: 3,
    RoomType.SLEEPBOX.value: 4,
    RoomType.WHOLE_HOUSE.value: 5,
}

ROOM_TYPE_ID_TO_CODE: dict[int, str] = {
    1: RoomType.ROOM.value,
    2: RoomType.STUDIO.value,
    3: RoomType.APARTMENT.value,
    4: RoomType.SLEEPBOX.value,
    5: RoomType.WHOLE_HOUSE.value,
}
