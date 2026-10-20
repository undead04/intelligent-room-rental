import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.geocode import GeocodeResponse
from app.schemas.response import ErrorDTO, ResponseDTO
from app.services.geocoder import resolve_location

logger = logging.getLogger(__name__)
router = APIRouter()

# Khung toạ độ Việt Nam (gồm cả Hoàng Sa, Trường Sa) để kiểm tra kết quả
VN_LAT_RANGE = (6.0, 23.5)
VN_LON_RANGE = (102.0, 118.0)


# ---------- Helpers ----------

def _in_vietnam(lat: float, lon: float) -> bool:
    return (
        VN_LAT_RANGE[0] <= lat <= VN_LAT_RANGE[1]
        and VN_LON_RANGE[0] <= lon <= VN_LON_RANGE[1]
    )


def _geocode_one(query: str, hint: Optional[str]) -> Optional[GeocodeResponse]:
    result = resolve_location(query, hint)
    if not result:
        return None
    if not _in_vietnam(result.lat, result.lon):
        return None
    logger.info("Geocoded '%s' to (%f, %f) via %s", query, result.lat, result.lon, result.provider)
    return result


# ---------- Endpoints ----------
@router.get(
    "/",
    response_model=ResponseDTO[GeocodeResponse],
    responses={404: {"model": ErrorDTO}, 422: {"model": ErrorDTO}, 500: {"model": ErrorDTO}},
    summary="Tìm toạ độ một địa điểm / trường học",
)
def geocode(
    q: str = Query(..., min_length=2, max_length=200, description="Địa điểm cần tìm"),
    hint: Optional[str] = Query(None, max_length=100, description="Tỉnh/thành, vd: Đà Nẵng"),
):
    result = _geocode_one(q, hint)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy toạ độ cho '{q}'. Thử thêm hint (tỉnh/thành) hoặc nhập cụ thể hơn.",
        )
    return ResponseDTO[GeocodeResponse](data=result)
