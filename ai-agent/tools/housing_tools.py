"""Native LangChain tools để tìm kiếm và ra quyết định phòng trọ.
Gọi trực tiếp Backend API qua HTTP mà không cần qua bash hay subprocess.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional
import httpx
from langchain_core.tools import tool

API_BASE = os.environ.get("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
TIMEOUT = float(os.environ.get("SEARCH_ROOM_TIMEOUT", "20.0"))


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=TIMEOUT)


def _unwrap_response(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": f"Phản hồi không phải JSON: {resp.text[:200]}"}

    if isinstance(data, dict) and "data" in data and "success" in data:
        if not data.get("success", False):
            return {"ok": False, "error": data.get("message", "API trả về lỗi")}
        return {"ok": True, "data": data["data"]}
    return {"ok": True, "data": data}


@tool
def geocode_location(query: str, hint: str = "Hồ Chí Minh") -> str:
    """Chuyển đổi tên địa điểm, trường đại học, toà nhà hoặc tên đường thành toạ độ (lat, lng).

    Args:
        query: Tên địa điểm cần tìm (ví dụ: 'Trường Đại học Công nghệ Thông tin', 'Ký túc xá khu B', 'Đường D2 Bình Thạnh').
        hint: Gợi ý tỉnh/thành phố để thu hẹp tìm kiếm (mặc định 'Hồ Chí Minh').

    Returns:
        JSON string chứa {lat, lon, formatted_address} hoặc thông báo lỗi nếu không tìm thấy.
    """
    try:
        with _client() as client:
            resp = client.get("/geocode", params={"q": query, "hint": hint})
            if resp.status_code == 404:
                return json.dumps({
                    "ok": False,
                    "error": f"Không tìm thấy toạ độ cho '{query}'. Hãy thử nhập cụ thể hơn hoặc hỏi lại người dùng."
                }, ensure_ascii=False)
            if resp.is_error:
                return json.dumps({
                    "ok": False,
                    "error": f"HTTP {resp.status_code}: {resp.text}"
                }, ensure_ascii=False)
            unwrapped = _unwrap_response(resp)
            return json.dumps(unwrapped, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": f"Không thể kết nối đến Geocode API ({API_BASE}/geocode): {str(e)}"
        }, ensure_ascii=False)


@tool
def get_location_hierarchy(
    city_name: Optional[str] = None,
    district_name: Optional[str] = None,
    ward_name: Optional[str] = None,
    city_id: Optional[int] = None,
    district_id: Optional[int] = None,
) -> str:
    """Tra cứu ID của Thành phố, Quận/Huyện, Phường/Xã từ cơ sở dữ liệu.
    Dùng khi người dùng tìm kiếm theo khu vực hành chính (ví dụ: 'tìm phòng ở Linh Xuân', 'tìm phòng ở Quận 1').

    Args:
        city_name: Tên thành phố để tìm kiếm (ví dụ 'Hồ Chí Minh').
        district_name: Tên quận/huyện để tìm kiếm (ví dụ 'Thủ Đức', 'Bình Thạnh').
        ward_name: Tên phường/xã để tìm kiếm (ví dụ 'Linh Trung', 'Linh Xuân').
        city_id: ID thành phố (nếu đã biết, dùng để lọc quận chính xác).
        district_id: ID quận/huyện (nếu đã biết, dùng để lọc phường chính xác).

    Returns:
        JSON danh sách các địa danh khớp kèm ID tương ứng.
    """
    try:
        with _client() as client:
            # 1. Tra cứu phường nếu có yêu cầu
            if ward_name or district_id:
                params = {}
                if district_id:
                    params["district_id"] = district_id
                if ward_name:
                    params["search"] = ward_name
                resp = client.get("/locations/wards", params=params)
                unwrapped = _unwrap_response(resp)
                return json.dumps(unwrapped, ensure_ascii=False)

            # 2. Tra cứu quận nếu có yêu cầu
            if district_name or city_id:
                params = {}
                if city_id:
                    params["city_id"] = city_id
                if district_name:
                    params["search"] = district_name
                resp = client.get("/locations/districts", params=params)
                unwrapped = _unwrap_response(resp)
                return json.dumps(unwrapped, ensure_ascii=False)

            # 3. Tra cứu thành phố
            params = {}
            if city_name:
                params["search"] = city_name
            resp = client.get("/locations/cities", params=params)
            unwrapped = _unwrap_response(resp)
            return json.dumps(unwrapped, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": f"Lỗi kết nối Locations API: {str(e)}"
        }, ensure_ascii=False)


@tool
def search_rooms(
    query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    city_id: Optional[int] = None,
    district_id: Optional[int] = None,
    ward_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    amenities: Optional[list[str]] = None,
    limit: int = 5,
) -> str:
    """Tìm kiếm phòng trọ bằng Vector Search kết hợp Rerank đa tiêu chí từ Backend.

    Hệ thống sẽ lọc theo các ràng buộc cứng (giá, vị trí/toạ độ, diện tích) và tính toán điểm phù hợp
    (match_score) kèm bản giải thích chi tiết (explain_match: điểm giá, an ninh, tiện ích, vị trí, ngữ nghĩa).

    Args:
        query: Câu mô tả nhu cầu bằng ngôn ngữ tự nhiên (ví dụ: 'phòng trọ có gác lửng, yên tĩnh, cho nuôi mèo, giờ giấc tự do').
        lat: Vĩ độ của điểm mốc (lấy từ geocode_location nếu người dùng tìm quanh một địa điểm).
        lng: Kinh độ của điểm mốc.
        city_id: ID thành phố (lấy từ get_location_hierarchy).
        district_id: ID quận/huyện.
        ward_id: ID phường/xã.
        min_price: Giá tối thiểu bằng VNĐ (ví dụ: 1500000).
        max_price: Giá tối đa bằng VNĐ (ví dụ: 3500000).
        min_area: Diện tích tối thiểu (m²).
        max_area: Diện tích tối đa (m²).
        amenities: Danh sách tiện ích yêu cầu (ví dụ: ['wifi', 'parking', 'ac']).
        limit: Số lượng phòng tối đa cần lấy (mặc định 5).

    Returns:
        JSON string chứa danh sách phòng phù hợp nhất kèm match_score và explain_match của từng phòng.
    """
    params: dict[str, Any] = {"limit": limit, "offset": 0}
    if lat is not None:
        params["lat"] = lat
    if lng is not None:
        params["lng"] = lng
    if city_id is not None:
        params["city_id"] = city_id
    if district_id is not None:
        params["district_id"] = district_id
    if ward_id is not None:
        params["ward_id"] = ward_id
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price
    if min_area is not None:
        params["min_area"] = min_area
    if max_area is not None:
        params["max_area"] = max_area

    body: dict[str, Any] = {"query": query}
    if amenities:
        body["amenities"] = amenities

    try:
        with _client() as client:
            resp = client.post("/listings/vector-search", params=params, json=body)
            if resp.is_error:
                return json.dumps({
                    "ok": False,
                    "error": f"HTTP {resp.status_code}: {resp.text}"
                }, ensure_ascii=False)
            unwrapped = _unwrap_response(resp)
            return json.dumps(unwrapped, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": f"Không thể kết nối đến Vector Search API ({API_BASE}/listings/vector-search): {str(e)}"
        }, ensure_ascii=False)


@tool
def get_listing_detail(listing_id: str) -> str:
    """Lấy thông tin chi tiết đầy đủ của một tin đăng phòng trọ cụ thể theo ID.

    Args:
        listing_id: Mã ID của tin đăng (ví dụ: 'nhatot_134860847').

    Returns:
        JSON chi tiết tin đăng (mô tả đầy đủ, hình ảnh, thông tin liên hệ, tiền cọc, điểm an ninh).
    """
    try:
        with _client() as client:
            resp = client.get(f"/listings/{listing_id}")
            if resp.status_code == 404:
                return json.dumps({
                    "ok": False,
                    "error": f"Không tìm thấy tin đăng với mã '{listing_id}'."
                }, ensure_ascii=False)
            if resp.is_error:
                return json.dumps({
                    "ok": False,
                    "error": f"HTTP {resp.status_code}: {resp.text}"
                }, ensure_ascii=False)
            unwrapped = _unwrap_response(resp)
            return json.dumps(unwrapped, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": f"Không thể lấy thông tin chi tiết phòng ({listing_id}): {str(e)}"
        }, ensure_ascii=False)
