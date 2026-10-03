from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.models.room_type import RoomType
from app.schemas.analytics import PriceStatsResponse
from app.schemas.listing import ListingDetailResponse, ListingResponse

router = APIRouter()


def filtered_query(
    db: Session,
    search: Optional[str],
    city_id: Optional[int],
    district_id: Optional[int],
    ward_id: Optional[int],
    room_type_id: Optional[int],
    min_price: Optional[float],
    max_price: Optional[float],
    min_area: Optional[float],
    max_area: Optional[float],
):
    query = db.query(Listing).options(
        joinedload(Listing.city),
        joinedload(Listing.district),
        joinedload(Listing.ward),
        joinedload(Listing.room_type),
    )
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Listing.title.ilike(pattern), Listing.address_raw.ilike(pattern)))
    if city_id is not None:
        query = query.filter(Listing.region_id == city_id)
    if district_id is not None:
        query = query.filter(Listing.district_id == district_id)
    if ward_id is not None:
        query = query.filter(Listing.ward_id == ward_id)
    if room_type_id is not None:
        query = query.filter(Listing.room_type_id == room_type_id)
    if min_price is not None:
        query = query.filter(Listing.price_vnd >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price_vnd <= max_price)
    if min_area is not None:
        query = query.filter(Listing.area_m2 >= min_area)
    if max_area is not None:
        query = query.filter(Listing.area_m2 <= max_area)
    return query


@router.get("/", response_model=List[ListingResponse], summary="Lấy danh sách tin đăng")
def get_listings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    district: Optional[str] = None,
    city_id: Optional[int] = Query(None, ge=1),
    district_id: Optional[int] = Query(None, ge=1),
    ward_id: Optional[int] = Query(None, ge=1),
    room_type_id: Optional[int] = Query(None, ge=1),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_area: Optional[float] = Query(None, ge=0),
    max_area: Optional[float] = Query(None, ge=0),
    db: Session = Depends(get_db),
):
    query = filtered_query(
        db, search, city_id, district_id, ward_id, room_type_id,
        min_price, max_price, min_area, max_area,
    )
    if district:
        query = query.join(District).filter(District.name.ilike(f"%{district}%"))
    return query.order_by(Listing.list_id.desc()).offset(offset).limit(limit).all()


@router.get("/price-stats", response_model=PriceStatsResponse, summary="Tra cứu thống kê giá phòng")
def get_price_stats(
    city_id: Optional[int] = Query(None, ge=1),
    district_id: Optional[int] = Query(None, ge=1),
    room_type_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    query = db.query(
        func.count(Listing.list_id),
        func.avg(Listing.price_vnd),
        func.min(Listing.price_vnd),
        func.max(Listing.price_vnd),
        func.avg(Listing.area_m2),
    ).filter(Listing.price_vnd.isnot(None))
    if city_id is not None:
        query = query.filter(Listing.region_id == city_id)
    if district_id is not None:
        query = query.filter(Listing.district_id == district_id)
    if room_type_id is not None:
        query = query.filter(Listing.room_type_id == room_type_id)
    total, average, minimum, maximum, average_area = query.one()
    return PriceStatsResponse(
        city=str(city_id) if city_id else None,
        district=str(district_id) if district_id else None,
        room_type=str(room_type_id) if room_type_id else None,
        total_listings=total or 0,
        average_price_vnd=average,
        minimum_price_vnd=minimum,
        maximum_price_vnd=maximum,
        average_area_m2=average_area,
    )


@router.get("/{list_id}", response_model=ListingDetailResponse, summary="Lấy chi tiết tin đăng")
def get_listing_by_id(list_id: int, db: Session = Depends(get_db)):
    listing = (
        db.query(Listing)
        .options(
            joinedload(Listing.poster),
            joinedload(Listing.city),
            joinedload(Listing.district),
            joinedload(Listing.ward),
            joinedload(Listing.room_type),
        )
        .filter(Listing.list_id == list_id)
        .one_or_none()
    )
    if listing is None:
        raise HTTPException(status_code=404, detail=f"Listing with id '{list_id}' not found")
    return listing
