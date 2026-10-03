from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import City, District, Ward
from app.schemas.location import CityResponse, DistrictResponse, WardResponse

router = APIRouter()


@router.get("/cities", response_model=List[CityResponse], summary="Lấy danh sách tỉnh/thành phố")
def get_cities(
    search: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(City)
    if search:
        query = query.filter(City.name.ilike(f"%{search}%"))
    return query.order_by(City.name).all()


@router.get("/districts", response_model=List[DistrictResponse], summary="Lấy danh sách quận/huyện")
def get_districts(
    city_id: Optional[int] = Query(default=None, ge=1),
    search: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(District)
    if city_id is not None:
        query = query.filter(District.city_id == city_id)
    if search:
        query = query.filter(District.name.ilike(f"%{search}%"))
    return query.order_by(District.name).all()


@router.get("/wards", response_model=List[WardResponse], summary="Lấy danh sách phường/xã")
def get_wards(
    district_id: Optional[int] = Query(default=None, ge=1),
    search: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(Ward)
    if district_id is not None:
        query = query.filter(Ward.district_id == district_id)
    if search:
        query = query.filter(Ward.name.ilike(f"%{search}%"))
    return query.order_by(Ward.name).all()
