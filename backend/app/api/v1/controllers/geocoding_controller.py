from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from app.schemas.geocode import GeocodeResponse

# Đổi tên module cho khớp với file service của bạn
from app.services.geocoder import resolve_location
from app.schemas.response import ResponseDTO

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
    print(f"Geocoded '{query}' to ({result.lat}, {result.lon}) via {result.provider}")
    return result


# ---------- Endpoints ----------

@router.get("", response_model=ResponseDTO[GeocodeResponse], summary="Tìm toạ độ một địa điểm")
@router.get("/", response_model=ResponseDTO[GeocodeResponse], summary="Tìm toạ độ một địa điểm", include_in_schema=False)
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
    return ResponseDTO[GeocodeResponse](
        success=True,
        status=200,
        code="OK",
        data=result,
        message="Request completed successfully",
    )



# @router.post("/batch", response_model=BatchResponse, summary="Tìm toạ độ nhiều địa điểm")
# def geocode_batch(body: BatchRequest):
#     # Chạy tuần tự để không vượt rate limit 1 req/s của Nominatim công cộng
#     items: List[BatchItem] = []
#     for q in body.queries:
#         q = q.strip()
#         if len(q) < 2:
#             items.append(BatchItem(query=q, found=False))
#             continue
#         result = _geocode_one(q, body.hint)
#         items.append(BatchItem(query=q, found=result is not None, result=result))

#     return BatchResponse(
#         total=len(items),
#         found=sum(1 for i in items if i.found),
#         items=items,
#     )


# @router.get("/health", summary="Kiểm tra service")
# def health():
#     return {"status": "ok"}