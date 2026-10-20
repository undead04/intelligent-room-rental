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
    VectorSearchQueryFilters,
    VectorSearchResult,
)
from app.schemas.listing_count import ListingCountResponse
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
):
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
):
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
):
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
):
    listings = service.get_listings_by_ids(ids=body.ids, preserve_order=True)
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
    filters: VectorSearchQueryFilters = Depends(),
    service: ListingService = Depends(get_listing_service),
):
    """Tìm kiếm tin đăng theo vector embedding (hỗ trợ filters qua Query params hoặc trực tiếp trong Body)."""
    embedding_model = request.app.state.embedding_model

    # Linh hoạt lấy filter: ưu tiên JSON Body, fallback về Query params
    lat = body.lat if body.lat is not None else filters.lat
    lng = body.lng if body.lng is not None else filters.lng
    city_id = body.city_id if body.city_id is not None else filters.city_id
    district_id = body.district_id if body.district_id is not None else filters.district_id
    ward_id = body.ward_id if body.ward_id is not None else filters.ward_id
    min_price = body.min_price if body.min_price is not None else filters.min_price
    max_price = body.max_price if body.max_price is not None else filters.max_price
    min_area = body.min_area if body.min_area is not None else filters.min_area
    max_area = body.max_area if body.max_area is not None else filters.max_area
    limit = body.limit if body.limit is not None else filters.limit
    offset = body.offset if body.offset is not None else filters.offset

    results = service.vector_search(
        query=body.query,
        amenities=body.amenities,
        weights=body.weights,
        model_embedding=embedding_model,
        city_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        min_price=min_price,
        max_price=max_price,
        max_area=max_area,
        min_area=min_area,
        limit=limit,
        lat=lat,
        lng=lng,
        offset=offset,
    )
    return ResponseDTO[list[VectorSearchResult]](data=results)


@router.get(
    "/{list_id}",
    response_model=ResponseDTO[ListingDetailResponse],
    responses={404: {"model": ErrorDTO}, 422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Lấy chi tiết tin đăng",
)
def get_listing_by_id(list_id: str, service: ListingService = Depends(get_listing_service)):
    return ResponseDTO[ListingDetailResponse](data=service.get_listing(list_id))
