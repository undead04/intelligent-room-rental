"""Tool nhà ở cho agent (LangChain) + các HÀM LÕI để graph gọi thẳng (không qua JSON/tool).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.tools import tool

from domain.enums import normalize_amenities, normalize_room_type
from domain.schemas import format_vnd_million
from skills.skills_discovery import discover_housing_skills, get_skill
from tools.http import request
from tools.location_service import infer_region_from_location_text, resolve_admin, resolve_location

logger = logging.getLogger(__name__)

MAX_LIMIT = 20
_LISTING_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


# =============================================================================
# Hành chính
# =============================================================================
_PATHS = {"city": "/locations/cities", "district": "/locations/districts", "ward": "/locations/wards"}


def admin_lookup(level: str, name: str, city_id: Optional[int] = None, district_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Tra bảng hành chính (server-side `search`). Lỗi -> []. Đây là `AdminLookup` của location_service."""
    params: dict[str, Any] = {"search": name}
    if level == "district" and city_id is not None:
        params["city_id"] = city_id
    if level == "ward" and district_id is not None:
        params["district_id"] = district_id
    res = request("GET", _PATHS[level], params=params)
    return res["data"] if res.get("ok") and isinstance(res.get("data"), list) else []


# =============================================================================
# Định vị điểm
# =============================================================================
def _parse_geocode_payload(data: Any) -> Optional[dict[str, Any]]:
    """Chuẩn hoá response.data từ Backend /geocode (1 điểm hoặc danh sách ambiguous)."""
    if not isinstance(data, dict):
        return None
    if data.get("ambiguous") and isinstance(data.get("candidates"), list):
        cands: list[dict[str, Any]] = []
        for item in data["candidates"]:
            if not isinstance(item, dict):
                continue
            lat = item.get("lat")
            lng = item.get("lon", item.get("lng"))
            if lat is None or lng is None:
                continue
            cands.append(
                {
                    "name": str(item.get("name") or item.get("formatted_address") or ""),
                    "lat": float(lat),
                    "lng": float(lng),
                    "address": str(item.get("formatted_address") or ""),
                    "provider": str(item.get("provider") or ""),
                }
            )
        if cands:
            return {"ambiguous": True, "candidates": cands}
        return None
    if data.get("lat") is not None:
        lng = data.get("lon", data.get("lng"))
        if lng is not None:
            return {"lat": float(data["lat"]), "lng": float(lng)}
    return None


def geocode_point(query: str, hint: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Hàm lõi: gọi thẳng Backend `/geocode(query, hint)` (0 LLM, luôn giữ nguyên hint vùng)."""
    q = (query or "").strip()
    if not q:
        return None
    params: dict[str, str] = {"q": q}
    h = (hint or "").strip()
    if h:
        params["hint"] = h
    res = request("GET", "/geocode", params=params)
    if res.get("ok"):
        return _parse_geocode_payload(res.get("data"))
    return None


# =============================================================================
# Tìm phòng / chi tiết / thống kê giá
# =============================================================================
def search_rooms_api(args: dict[str, Any]) -> dict[str, Any]:
    """Hàm lõi: gọi vector-search. args cùng tên với tool. Trả {"ok", "data"|"error", ...}; KHÔNG ném lỗi."""
    lat, lng = args.get("lat"), args.get("lng")
    raw_q = str(args.get("query") or "").strip()
    query_str = raw_q if raw_q else "phòng trọ"
    body: dict[str, Any] = {"query": query_str, "limit": max(1, min(int(args.get("limit") or 5), MAX_LIMIT)), "offset": 0}
    if lat is not None:
        body["lat"] = lat
    if lng is not None:
        body["lng"] = lng
    if lat is None and lng is None:            # có toạ độ thì không gửi ID hành chính (tránh xung đột bán kính)
        for k in ("city_id", "district_id", "ward_id"):
            if args.get(k) is not None:
                body[k] = args[k]
    for k in ("min_price", "max_price", "min_area", "max_area", "min_bedrooms", "min_bathrooms"):
        if args.get(k) is not None:
            body[k] = getattr(args[k], "value", args[k])
    if args.get("room_type") is not None:
        rt = args["room_type"]
        if isinstance(rt, (list, tuple, set)):
            body["room_type"] = [getattr(r, "value", r) for r in rt]
        else:
            body["room_type"] = getattr(rt, "value", rt)
    amenities = [a.value for a in normalize_amenities(args.get("amenities"))]
    if amenities:
        body["amenities"] = sorted(amenities)
    pref_amenities = [a.value for a in normalize_amenities(args.get("preferred_amenities"))]
    if pref_amenities:
        body["preferred_amenities"] = sorted(pref_amenities)
    if args.get("max_distance_km") is not None:
        body["max_distance_km"] = max(0.5, min(50.0, float(args["max_distance_km"])))
    if args.get("excluded_room_types"):
        body["excluded_room_types"] = [getattr(r, "value", r) for r in args["excluded_room_types"]]
    if args.get("weights"):
        body["weights"] = args["weights"]
    if args.get("prefer_cheapest") is not None:
        body["prefer_cheapest"] = bool(args["prefer_cheapest"])
    if args.get("include_amenity_overall") is not None:
        body["include_amenity_overall"] = bool(args["include_amenity_overall"])

    res = request("POST", "/listings/vector-search", json=body)
    if res.get("ok") and not res.get("data"):
        res["data"] = []
        res.update(_empty_result_hints(args, amenities))
    return res


def _empty_result_hints(args: dict[str, Any], amenities: list[str]) -> dict[str, Any]:
    suggestions: list[str] = []
    if args.get("max_price"):
        suggestions.append("cân nhắc điều chỉnh hoặc nới nhẹ ngân sách")
    if args.get("ward_id") is not None:
        suggestions.append("mở rộng tìm kiếm ra toàn Quận/Huyện thay vì chỉ 1 Phường")
    elif args.get("district_id") is not None or (args.get("lat") is not None and args.get("lng") is not None):
        suggestions.append("mở rộng phạm vi sang các quận/khu vực lân cận")
    if amenities:
        suggestions.append(f"lược bớt một số tiện ích bắt buộc ({', '.join(amenities)})")
    if args.get("min_area"):
        suggestions.append(f"giảm nhẹ yêu cầu diện tích tối thiểu ({float(args['min_area']):g}m²)")
    hint = ", hoặc ".join(suggestions) or "điều chỉnh lại mức giá hoặc mở rộng khu vực tìm kiếm"
    return {"context_suggestions": suggestions,
            "message": ("Truy vấn search_rooms trả về 0 phòng phù hợp với bộ lọc hiện tại. "
                        f"Hãy tư vấn khách quan cho người dùng dựa trên ngữ cảnh: gợi ý {hint}.")}


@tool
def search_rooms(
    query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    city_id: Optional[int] = None,
    district_id: Optional[int] = None,
    ward_id: Optional[int] = None,
    room_type: Optional[str | list[str]] = None,
    excluded_room_types: Optional[list[str]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    min_bedrooms: Optional[int] = None,
    amenities: Optional[list[str]] = None,
    preferred_amenities: Optional[list[str]] = None,
    max_distance_km: Optional[float] = None,
    weights: Optional[dict[str, float]] = None,
    prefer_cheapest: Optional[bool] = None,
    limit: int = 5,
) -> str:
    """Tìm kiếm phòng trọ bằng Vector Search kết hợp Rerank đa tiêu chí từ Backend.

    Hệ thống sẽ lọc theo các ràng buộc cứng (giá, loại phòng, vị trí/toạ độ, diện tích) và tính toán điểm phù hợp
    (match_score) kèm bản giải thích chi tiết (explain_match: điểm giá, an ninh, tiện ích, vị trí, ngữ nghĩa).

    Args:
        query: Câu mô tả nhu cầu bằng ngôn ngữ tự nhiên (ví dụ: 'phòng trọ có gác lửng, yên tĩnh, cho nuôi mèo, giờ giấc tự do').
        lat: Vĩ độ của điểm mốc (nếu người dùng tìm quanh một địa điểm).
        lng: Kinh độ của điểm mốc.
        city_id: ID thành phố.
        district_id: ID quận/huyện.
        ward_id: ID phường/xã.
        room_type: Mã loại phòng hoặc danh sách mã loại phòng (ROOM, STUDIO, APARTMENT, SLEEPBOX, WHOLE_HOUSE).
        excluded_room_types: Danh sách mã loại phòng bị loại trừ.
        min_price: Giá tối thiểu bằng VNĐ (ví dụ: 1500000).
        max_price: Giá tối đa bằng VNĐ (ví dụ: 3500000).
        min_area: Diện tích tối thiểu (m²).
        max_area: Diện tích tối đa (m²).
        min_bedrooms: Số phòng ngủ tối thiểu.
        amenities: Danh sách tiện ích yêu cầu theo format Amenity (ví dụ: ['aircon', 'mezzanine', 'pet_allowed']).
        preferred_amenities: Danh sách tiện ích ưu tiên mềm.
        max_distance_km: Bán kính tìm kiếm tối đa (km).
        weights: Trọng số động tùy chỉnh (e.g. {'price': 0.35, 'location': 0.35, ...}).
        limit: Số lượng phòng tối đa cần lấy (mặc định 5).

    Returns:
        JSON string chứa danh sách phòng phù hợp nhất kèm match_score và explain_match của từng phòng.
    """
    return dump(search_rooms_api(dict(
        query=query, lat=lat, lng=lng, city_id=city_id, district_id=district_id, ward_id=ward_id,
        room_type=room_type, excluded_room_types=excluded_room_types,
        min_price=min_price, max_price=max_price, min_area=min_area, max_area=max_area,
        min_bedrooms=min_bedrooms,
        amenities=amenities, preferred_amenities=preferred_amenities, max_distance_km=max_distance_km,
        weights=weights, prefer_cheapest=prefer_cheapest, limit=limit,
    )))


def fetch_listing_detail(listing_id: str) -> dict[str, Any]:
    """Hàm lõi gọi Backend API: Lấy chi tiết phòng theo ID, trả về response dict đầy đủ (ok, data, status, error)."""
    clean = str(listing_id or "").strip()
    if not _LISTING_ID.match(clean):                        # whitelist: chống Path Traversal sang endpoint khác của backend
        return {"ok": False, "error": f"Mã tin đăng '{listing_id}' không hợp lệ."}
    res = request("GET", f"/listings/{clean}")
    if res.get("status") == 404:
        return {"ok": False, "error": f"Không tìm thấy tin đăng với mã '{clean}'."}
    return res


def compact_listing_detail(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Rút gọn và chuẩn hoá dữ liệu chi tiết phòng trọ từ Backend (ListingDetailResponse):
    - Chuẩn hoá key: address_raw -> address, price_vnd -> price/price_million
    - Bóc tách tiện ích & thú cưng từ concept_scores sang tiếng Việt
    - Bóc tách tên người liên hệ từ poster
    - Loại bỏ ảnh CDN và metadata crawl cồng kềnh
    Giảm ~75% token bloat cho LLM context."""
    if not isinstance(raw_data, dict):
        return {}

    compact: dict[str, Any] = {}

    # 1. Nhận diện
    for k in ("id", "title"):
        if raw_data.get(k):
            compact[k] = raw_data[k]

    # 2. Giá phòng (hỗ trợ cả price_vnd từ backend và price/price_million nếu có)
    price_vnd = raw_data.get("price_vnd") or raw_data.get("price")
    if isinstance(price_vnd, (int, float)) and price_vnd > 0:
        compact["price"] = format_vnd_million(price_vnd)
        compact["price_million"] = round(price_vnd / 1_000_000, 2)
    elif raw_data.get("price_string"):
        compact["price"] = raw_data["price_string"]

    # 3. Tiền cọc (hỗ trợ deposit VND từ backend và deposit_million)
    deposit_vnd = raw_data.get("deposit")
    if isinstance(deposit_vnd, (int, float)) and deposit_vnd > 0:
        compact["deposit"] = deposit_vnd
        compact["deposit_million"] = round(deposit_vnd / 1_000_000, 2)

    # 4. Diện tích, số phòng & loại phòng (hỗ trợ object room_type từ backend)
    if raw_data.get("area_m2"):
        compact["area_m2"] = raw_data["area_m2"]
    if raw_data.get("bedrooms") is not None:
        compact["bedrooms"] = raw_data["bedrooms"]
    if raw_data.get("bathrooms") is not None:
        compact["bathrooms"] = raw_data["bathrooms"]

    room_type = raw_data.get("room_type")
    if isinstance(room_type, dict) and room_type.get("name"):
        compact["room_type_name"] = room_type["name"]

    # 5. Địa chỉ (Backend lưu address_raw hoặc lồng trong ward/district/city)
    address = raw_data.get("address_raw")
    if not address:
        ward = raw_data.get("ward") if isinstance(raw_data.get("ward"), dict) else {}
        district = raw_data.get("district") if isinstance(raw_data.get("district"), dict) else {}
        city = raw_data.get("city") if isinstance(raw_data.get("city"), dict) else {}
        parts = [
            ward.get("name"),
            district.get("name"),
            city.get("name")
        ]
        address = ", ".join(filter(None, parts))
    if address:
        compact["address"] = address

    # 6. Tiện ích & Quy định (Backend lưu điểm ML trong concept_scores)
    concept_scores = raw_data.get("concept_scores") or {}
    amenities = []
    if isinstance(concept_scores, dict):
        from domain.schemas import _CONCEPT_TAGS
        for k, label in _CONCEPT_TAGS.items():
            score = concept_scores.get(k)
            if isinstance(score, (int, float)) and score >= 0.5 and label not in amenities:
                amenities.append(label)

        if "pet_allowed" in concept_scores and raw_data.get("pet_allowed") is None:
            compact["pet_allowed"] = bool(concept_scores["pet_allowed"] >= 0.5)

    if amenities:
        compact["amenities"] = amenities

    # 8. Người liên hệ (Backend lồng trong poster)
    poster = raw_data.get("poster")
    if isinstance(poster, dict) and poster.get("name"):
        compact["contact_name"] = poster["name"]
    
    # 9. Mô tả phòng (cắt bớt nếu quá 1500 ký tự)
    desc = raw_data.get("description")
    if isinstance(desc, str) and desc:
        compact["description"] = desc[:1500] + "... (đã rút gọn)" if len(desc) > 1500 else desc

    return compact


@tool
def get_listing_detail(listing_id: str) -> str:
    """Lấy thông tin chi tiết đầy đủ của một tin đăng phòng trọ cụ thể theo ID.

    Args:
        listing_id: Mã ID của tin đăng (ví dụ: 'nhatot_134860847').

    Returns:
        JSON chi tiết tin đăng (mô tả, thông tin liên hệ, tiền cọc, điểm an ninh, chi phí).
    """
    res = fetch_listing_detail(listing_id)
    if res.get("ok") and isinstance(res.get("data"), dict):
        compacted = compact_listing_detail(res["data"])
        return dump({"ok": True, "data": compacted})
    return dump(res)


def fetch_full_price_stats(
    city_id: Optional[int],
    district_id: Optional[int] = None,
    room_type_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Hàm lõi: trả toàn bộ payload `/listings/price-stats` (`price_stats_general` + `price_stats_by_area`) hoặc None."""
    if city_id is None:
        return None
    params = {
        "city_id": city_id,
        **({"district_id": district_id} if district_id is not None else {}),
        **({"room_type_id": room_type_id} if room_type_id is not None else {}),
    }
    res = request("GET", "/listings/price-stats", params=params)
    data = res.get("data") if res.get("ok") else None
    return data if isinstance(data, dict) else None


def fetch_price_stats(city_id: Optional[int], district_id: Optional[int] = None, room_type_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    """Hàm lõi: `price_stats_general` hoặc None (lỗi/thiếu dữ liệu). Thiếu city_id -> None (không đoán thành phố)."""
    data = fetch_full_price_stats(city_id, district_id=district_id, room_type_id=room_type_id)
    return data.get("price_stats_general") if isinstance(data, dict) else None


def lookup_market_price_stats(
    location_text: str,
    *,
    room_type: Optional[str] = None,
    region_hint: Optional[str] = None,
    location_kind: Optional[str] = None,
    admin_lookup_fn: Optional[Any] = None,
    geocode_fn: Optional[Any] = None,
    price_stats_fn: Optional[Any] = None,
    nearby_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Phân giải khu vực và tra cứu thống kê giá phòng trọ thực tế từ Backend."""
    loc = (location_text or "").strip()
    if not loc:
        return {"ok": False, "error": "MISSING_LOCATION", "message": "Chưa có tên quận/huyện hoặc tỉnh/thành phố cần tra cứu giá."}

    rt = normalize_room_type(room_type)
    room_type_id = rt.type_id if rt is not None else None
    if room_type and rt is None:
        return {"ok": False, "error": "INVALID_ROOM_TYPE", "message": f"Loại phòng '{room_type}' không hợp lệ."}

    adm_fn = admin_lookup_fn or admin_lookup
    geo_fn = geocode_fn or geocode_point
    stats_fn = price_stats_fn or fetch_full_price_stats
    near_fn = nearby_fn or fetch_nearby_locations
    effective_hint = region_hint or infer_region_from_location_text(loc)

    res = resolve_admin(loc, adm_fn, region_hint=effective_hint)
    if res.kind == "admin" and res.city_id is not None:
        payload = stats_fn(res.city_id, res.district_id, room_type_id)
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "error": "BACKEND_UNAVAILABLE",
                "location": loc,
                "message": "Không lấy được số liệu thống kê giá từ máy chủ lúc này.",
            }
        # Hỗ trợ cả caller trả dict đầy đủ lẫn chỉ trả price_stats_general
        general = payload.get("price_stats_general") if "price_stats_general" in payload else payload
        if not isinstance(general, dict):
            general = {}
        by_area = payload.get("price_stats_by_area") if isinstance(payload.get("price_stats_by_area"), list) else []

        matched_ward = None
        if res.ward_id is not None:
            for item in by_area:
                if isinstance(item, dict) and item.get("area_id") == res.ward_id:
                    matched_ward = item
                    break

        return {
            "ok": True,
            "source": "price_stats",
            "location": loc,
            "city_id": res.city_id,
            "district_id": res.district_id,
            "ward_id": res.ward_id,
            "room_type": rt.label_vi if rt is not None else None,
            "total_listings": int(general.get("total_listings") or 0),
            "average_price_vnd": general.get("average_price_vnd"),
            "minimum_price_vnd": general.get("minimum_price_vnd"),
            "maximum_price_vnd": general.get("maximum_price_vnd"),
            "price_fluctuation_month": general.get("price_fluctuation_month"),
            "area_hotspot": general.get("area_hotspot"),
            "hotspot_posting_growth_month": general.get("hotspot_posting_growth_month"),
            "by_area": by_area[:5],
            "matched_ward_stats": matched_ward,
        }

    if res.kind == "ambiguous":
        return {
            "ok": False,
            "error": "AMBIGUOUS_LOCATION",
            "location": loc,
            "candidates": list(res.candidates or []),
            "message": f"Có nhiều địa danh khớp với '{loc}'.",
        }

    # Nếu không phải địa giới hành chính thuần (vd tên trường ĐH / KCN / địa điểm), thử geocode -> lấy thống kê vùng lân cận
    if location_kind != "admin":
        pt_res = resolve_location(loc, location_kind, adm_fn, geo_fn, region_hint=effective_hint)
        if pt_res.kind == "ambiguous":
            return {
                "ok": False,
                "error": "AMBIGUOUS_LOCATION",
                "location": loc,
                "candidates": list(pt_res.candidates or []),
                "message": f"Có nhiều địa điểm khớp với '{loc}'.",
            }
        if pt_res.kind == "point" and pt_res.lat is not None and pt_res.lng is not None:
            nearby = near_fn(
                lat=pt_res.lat,
                lng=pt_res.lng,
                room_type=rt.value if rt is not None else None,
                limit=4,
            )
            if nearby:
                return {
                    "ok": True,
                    "source": "nearby_areas",
                    "location": loc,
                    "room_type": rt.label_vi if rt is not None else None,
                    "nearby_areas": nearby[:4],
                }

    return {
        "ok": False,
        "error": "LOCATION_NOT_FOUND",
        "location": loc,
        "message": f"Không tìm thấy dữ liệu thống kê giá cho khu vực '{loc}'.",
    }


def fetch_nearby_locations(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    district_id: Optional[int] = None,
    ward_id: Optional[int] = None,
    city_id: Optional[int] = None,
    radius_km: float = 12.0,
    limit: int = 4,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    room_type: Optional[str] = None,
    amenities: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Tra cứu các quận/phường lân cận từ Backend API (/locations/nearby) kèm khoảng cách và thống kê giá thực tế."""
    params: dict[str, Any] = {"radius_km": radius_km, "limit": limit}
    if lat is not None:
        params["lat"] = lat
    if lng is not None:
        params["lng"] = lng
    if district_id is not None:
        params["district_id"] = district_id
    if ward_id is not None:
        params["ward_id"] = ward_id
    if city_id is not None:
        params["city_id"] = city_id
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price
    if room_type:
        params["room_type"] = getattr(room_type, "value", room_type)
    if amenities:
        params["amenities"] = [getattr(a, "value", str(a)) for a in amenities]

    res = request("GET", "/locations/nearby", params=params)
    data = res.get("data") if res.get("ok") else None
    return data if isinstance(data, list) else []


# =============================================================================
# Kỹ năng
# =============================================================================
def consult_skill(slug: str, query: Optional[str] = None) -> dict[str, Any]:
    """Hàm lõi: nội dung SKILL.md + references/*.md của skill `slug` (lấy trực tiếp từ RAM cache theo mtime => 0 Disk I/O lặp lại, không Path Traversal)."""
    skill = get_skill(slug)
    if skill is None:
        return {"ok": False, "error": f"Không tìm thấy kỹ năng '{slug}'. Hãy gọi list_housing_skills để xem danh sách kỹ năng khả dụng."}
    if getattr(skill, "instructions", ""):
        return {
            "ok": True,
            "skill_name": skill.slug,
            "instructions": skill.instructions,
            "references": dict(getattr(skill, "references", None) or {}),
        }
    from pathlib import Path

    try:
        f = Path(skill.path).resolve()
        refs: dict[str, str] = {}
        ref_dir = f.parent / "references"
        if ref_dir.is_dir():
            for r in sorted(ref_dir.glob("*.md")):
                refs[r.name] = r.read_text(encoding="utf-8")
        return {"ok": True, "skill_name": skill.slug, "instructions": f.read_text(encoding="utf-8"), "references": refs}
    except OSError:
        logger.warning("Lỗi đọc kỹ năng %s", slug, exc_info=True)
        return {"ok": False, "error": "Lỗi đọc nội dung kỹ năng."}


@tool
def list_housing_skills() -> str:
    """Liệt kê danh sách các Kỹ năng chuyên sâu (Housing Skills) hiện có trong hệ thống Homigo.
    Hệ thống hỗ trợ nạp thêm kỹ năng động bất cứ lúc nào (ví dụ: 'rental-contract-advisor').

    Returns:
        JSON danh sách các kỹ năng kèm mô tả công dụng.
    """
    return dump({"ok": True, "skills": [s.public_dict() for s in discover_housing_skills().values()]})


@tool
def consult_housing_skill(skill_name: str, query: Optional[str] = None) -> str:
    """Tra cứu và tham vấn tài liệu hướng dẫn chuyên sâu từ một Housing Skill (ví dụ: 'rental-contract-advisor').
    Dùng khi người dùng cần hỗ trợ về pháp lý, kiểm tra hợp đồng thuê trọ, bẫy tiền cọc hoặc các kỹ năng khác.

    Args:
        skill_name: Tên của kỹ năng muốn tham vấn (ví dụ: 'rental-contract-advisor').
        query: Câu hỏi hoặc nội dung điều khoản cụ thể cần tư vấn.

    Returns:
        JSON chứa toàn bộ nội dung hướng dẫn, checklist và lưu ý từ kỹ năng tương ứng.
    """
    return dump(consult_skill(skill_name, query))


@tool
def get_market_price_stats(location_text: str, room_type: Optional[str] = None) -> str:
    """Tra cứu thống kê mặt bằng giá phòng trọ thực tế (giá trung bình, thấp nhất, cao nhất, tổng tin đăng) theo khu vực.

    Args:
        location_text: Tên quận/huyện, tỉnh/thành phố hoặc địa điểm cần tra cứu (ví dụ: 'Gò Vấp', 'Quận 7, TP.HCM').
        room_type: Loại phòng tùy chọn ('ROOM', 'STUDIO', 'APARTMENT', 'SLEEPBOX', 'WHOLE_HOUSE').

    Returns:
        JSON chứa số liệu thống kê giá thực tế từ Backend hoặc thông báo lỗi nếu khu vực không xác định.
    """
    return dump(lookup_market_price_stats(location_text, room_type=room_type))
