from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.location import CityResponse, DistrictResponse, WardResponse
from app.schemas.response import ErrorDTO, ResponseDTO
from app.services.location_service import LocationService

router = APIRouter()


def get_location_service(db: Session = Depends(get_db)) -> LocationService:
    return LocationService(db)


@router.get(
    "/cities",
    response_model=ResponseDTO[list[CityResponse]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
)
def get_cities(
    search: Optional[str] = Query(None, min_length=1),
    service: LocationService = Depends(get_location_service),
):
    return ResponseDTO[list[CityResponse]](data=service.cities(search))


@router.get(
    "/districts",
    response_model=ResponseDTO[list[DistrictResponse]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
)
def get_districts(
    city_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = Query(None, min_length=1),
    service: LocationService = Depends(get_location_service),
):
    return ResponseDTO[list[DistrictResponse]](data=service.districts(city_id, search))


@router.get(
    "/wards",
    response_model=ResponseDTO[list[WardResponse]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
)
def get_wards(
    district_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = Query(None, min_length=1),
    service: LocationService = Depends(get_location_service),
):
    return ResponseDTO[list[WardResponse]](data=service.wards(district_id, search))
