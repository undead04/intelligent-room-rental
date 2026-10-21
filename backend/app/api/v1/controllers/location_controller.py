from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.location import CityResponse, DistrictResponse, NearbyLocationItem, WardResponse
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


@router.get(
    "/nearby",
    response_model=ResponseDTO[list[NearbyLocationItem]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
)
def get_nearby_locations(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    lng: Optional[float] = Query(None, ge=-180.0, le=180.0),
    district_id: Optional[int] = Query(None, ge=1),
    ward_id: Optional[int] = Query(None, ge=1),
    city_id: Optional[int] = Query(None, ge=1),
    radius_km: float = Query(12.0, ge=1.0, le=50.0),
    limit: int = Query(4, ge=1, le=10),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    room_type: Optional[str] = Query(None),
    amenities: Optional[list[str]] = Query(None),
    service: LocationService = Depends(get_location_service),
):
    """Tra cứu các quận/phường lân cận kèm khoảng cách và thống kê giá phòng từ cơ sở dữ liệu thực tế."""
    items = service.nearby_locations(
        lat=lat,
        lng=lng,
        district_id=district_id,
        ward_id=ward_id,
        city_id=city_id,
        radius_km=radius_km,
        limit=limit,
        min_price=min_price,
        max_price=max_price,
        room_type=room_type,
        amenities=amenities,
    )
    return ResponseDTO[list[NearbyLocationItem]](data=items)
