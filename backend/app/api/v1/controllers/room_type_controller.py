from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.services.location_service import LocationService
from app.api.v1.controllers.location_controller import get_location_service
from app.schemas.response import ErrorDTO, ResponseDTO
from app.schemas.room_type import RoomTypeResponse

router = APIRouter()


@router.get(
    "/",
    response_model=ResponseDTO[list[RoomTypeResponse]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
)
def get_room_types(
    search: Optional[str] = Query(None, min_length=1),
    service: LocationService = Depends(get_location_service),
):
    return ResponseDTO[list[RoomTypeResponse]](data=service.room_types(search))
