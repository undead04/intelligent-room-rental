from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.listing_service import ListingService
from app.schemas.analytics import PriceStatsResponse
from app.schemas.listing import ListingDetailResponse, ListingResponse
from app.schemas.listing_count import ListingCountResponse
from app.schemas.response import ErrorDTO, ResponseDTO

router = APIRouter()


def get_listing_service(db: Session = Depends(get_db)) -> ListingService:
    return ListingService(db)


@router.get(
    "/",
    response_model=ResponseDTO[list[ListingResponse]],
    responses={
        400: {"model": ErrorDTO},
        422: {"model": ErrorDTO},
        500: {"model": ErrorDTO},
    },
    summary="Lấy danh sách tin đăng",
)
def get_listings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    city_id: Optional[int] = Query(None, ge=1),
    district_id: Optional[int] = Query(None, ge=1),
    ward_id: Optional[int] = Query(None, ge=1),
    room_type_id: Optional[int] = Query(None, ge=1),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    order_by: str = Query("posted_date"),
    sort_desc: bool = Query(True),
    service: ListingService = Depends(get_listing_service),
):
    listings = service.list_listings(
        search=search, city_id=city_id, district_id=district_id,
        ward_id=ward_id, room_type_id=room_type_id, min_price=min_price,
        max_price=max_price, min_area=None, max_area=None, order_by=order_by,
        sort_desc=sort_desc, limit=limit, offset=offset,
    )
    return ResponseDTO[list[ListingResponse]](data=listings)


@router.get(
    "/total",
    response_model=ResponseDTO[ListingCountResponse],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Đếm tổng số tin đăng theo bộ lọc",
)
def get_total_listings(
    search: Optional[str] = None,
    city_id: Optional[int] = Query(None, ge=1),
    district_id: Optional[int] = Query(None, ge=1),
    ward_id: Optional[int] = Query(None, ge=1),
    room_type_id: Optional[int] = Query(None, ge=1),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_area: Optional[float] = Query(None, ge=0),
    max_area: Optional[float] = Query(None, ge=0),
    service: ListingService = Depends(get_listing_service),
):
    count = ListingCountResponse(
        total_listings=service.count_listings(
            search=search,
            city_id=city_id,
            district_id=district_id,
            ward_id=ward_id,
            room_type_id=room_type_id,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
        )
    )
    return ResponseDTO[ListingCountResponse](data=count)


@router.get(
    "/price-stats",
    response_model=ResponseDTO[PriceStatsResponse],
    responses={
        400: {"model": ErrorDTO},
        404: {"model": ErrorDTO},
        422: {"model": ErrorDTO},
        500: {"model": ErrorDTO},
    },
    summary="Tra cứu thống kê giá phòng",
)
def get_price_stats(
    city_id: int = Query(..., ge=1),
    district_id: Optional[int] = Query(None, ge=1),
    room_type_id: Optional[int] = Query(None, ge=1),
    service: ListingService = Depends(get_listing_service),
):
    return ResponseDTO[PriceStatsResponse](
        data=service.get_price_stats(city_id, district_id, room_type_id),
    )


@router.get(
    "/{list_id}",
    response_model=ResponseDTO[ListingDetailResponse],
    responses={404: {"model": ErrorDTO}, 422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Lấy chi tiết tin đăng",
)
def get_listing_by_id(list_id: str, service: ListingService = Depends(get_listing_service)):
    return ResponseDTO[ListingDetailResponse](data=service.get_listing(list_id))
