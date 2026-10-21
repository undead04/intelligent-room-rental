from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analytics import PriceStatsResponse
from app.schemas.listing import (
    ListingDetailResponse,
    ListingFilterParams,
    ListingIdsRequest,
    ListingQueryParams,
    ListingResponse,
    VectorSearchBody,
    VectorSearchResult,
    ListingCountResponse
)

from app.schemas.response import ErrorDTO, ResponseDTO
from app.services.listing_service import ListingService

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
    params: ListingQueryParams = Depends(),
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[list[ListingResponse]]:
    listings = service.list_listings(
        search=params.search,
        city_id=params.city_id,
        district_id=params.district_id,
        ward_id=params.ward_id,
        room_type_id=params.room_type_id,
        min_price=params.min_price,
        max_price=params.max_price,
        min_area=params.min_area,
        max_area=params.max_area,
        order_by=params.order_by,
        sort_desc=params.sort_desc,
        limit=params.limit,
        offset=params.offset,
    )
    return ResponseDTO[list[ListingResponse]](data=listings)


@router.get(
    "/total",
    response_model=ResponseDTO[ListingCountResponse],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Đếm tổng số tin đăng theo bộ lọc",
)
def get_total_listings(
    params: ListingFilterParams = Depends(),
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[ListingCountResponse]:
    count = ListingCountResponse(
        total_listings=service.count_listings(
            search=params.search,
            city_id=params.city_id,
            district_id=params.district_id,
            ward_id=params.ward_id,
            room_type_id=params.room_type_id,
            min_price=params.min_price,
            max_price=params.max_price,
            min_area=params.min_area,
            max_area=params.max_area,
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
    city_id: int = Query(..., ge=1, description="ID Tỉnh/Thành phố"),
    district_id: Optional[int] = Query(None, ge=1, description="ID Quận/Huyện"),
    room_type_id: Optional[int] = Query(None, ge=1, description="ID loại phòng"),
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[PriceStatsResponse]:
    return ResponseDTO[PriceStatsResponse](
        data=service.get_price_stats(city_id, district_id, room_type_id),
    )


@router.post(
    "/by-ids",
    response_model=ResponseDTO[list[ListingResponse]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Lấy danh sách tin đăng theo danh sách ID",
)
def get_listings_by_ids(
    body: ListingIdsRequest,
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[list[ListingResponse]]:
    listings = service.get_by_ids(ids=body.ids, preserve_order=True)
    return ResponseDTO[list[ListingResponse]](data=listings)


@router.post(
    "/vector-search",
    response_model=ResponseDTO[list[VectorSearchResult]],
    responses={422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Tìm kiếm tin đăng theo vector embedding kết hợp MCDM Rerank",
)
def vector_search_listings(
    request: Request,
    body: VectorSearchBody,
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[list[VectorSearchResult]]:
    """Tìm kiếm tin đăng theo vector embedding. Toàn bộ tham số được nhận trực tiếp qua JSON Body."""
    embedding_model = request.app.state.embedding_model

    results = service.vector_search(
        query=body.query,
        model_embedding=embedding_model,
        lat=body.lat,
        lng=body.lng,
        amenities=body.amenities,
        weights=body.weights,
        city_id=body.city_id,
        district_id=body.district_id,
        ward_id=body.ward_id,
        room_type_id=body.room_type_id,
        room_type=body.room_type,
        min_price=body.min_price,
        max_price=body.max_price,
        min_area=body.min_area,
        max_area=body.max_area,
        limit=body.limit,
        offset=body.offset,
    )
    return ResponseDTO[list[VectorSearchResult]](data=results)


@router.get(
    "/{list_id}",
    response_model=ResponseDTO[ListingDetailResponse],
    responses={404: {"model": ErrorDTO}, 422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Lấy chi tiết tin đăng",
)
def get_listing_by_id(
    list_id: str,
    service: ListingService = Depends(get_listing_service),
) -> ResponseDTO[ListingDetailResponse]:
    return ResponseDTO[ListingDetailResponse](data=service.get_listing(list_id))
