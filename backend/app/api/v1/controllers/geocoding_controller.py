import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.geocode import GeocodeResponse
from app.schemas.response import ErrorDTO, ResponseDTO
from app.services.geocoder import resolve_location

logger = logging.getLogger(__name__)
router = APIRouter()

def _geocode_one(query: str, hint: Optional[str]) -> Optional[GeocodeResponse]:
    result = resolve_location(query, hint)
    if not result:
        return None
    logger.info("Geocoded '%s' to (%f, %f) via %s", query, result.lat, result.lon, result.provider)
    return result

def _is_in_vietnam(lat: float, lon: float) -> bool:
    """Kiểm tra tọa độ có nằm trong phạm vi Việt Nam không"""
    return 8.1 <= lat <= 23.4 and 102.1 <= lon <= 109.6
    
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
    
    if not _is_in_vietnam(result.lat, result.lon):
        raise HTTPException(
            status_code=422,
            detail=f"Tọa độ tìm được ngoài Việt Nam: ({result.lat}, {result.lon}). Nhập lại query.",
        )
    return ResponseDTO[GeocodeResponse](data=result)
