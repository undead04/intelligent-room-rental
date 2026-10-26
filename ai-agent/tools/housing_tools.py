"""Tool nhà ở cho agent (LangChain) + các HÀM LÕI để graph gọi thẳng (không qua JSON/tool).



Thay đổi so với bản cũ:

  - KHÔNG gọi LLM trong tool để phân loại hành chính/chuẩn hoá tên/trích ngân sách (graph đã làm bằng NLU); chỉ còn một lần mở rộng

    địa danh bằng LLM khi /geocode trả 404 (đường dự phòng thật sự).

  - Phân loại hành chính bằng khớp tên CHÍNH XÁC với dữ liệu hành chính (location_service), không phải đoán bằng LLM/từ khoá.

  - Bỏ ngữ cảnh ẩn (contextvars) và khối ghi đè query/limit/weights/tiện ích trong search_rooms (đã gây mất trọng số MCDM ở nhánh agent).

    `set_turn_query_context`/`clear_turn_query_context` còn lại như no-op (DeprecationWarning) để mã cũ không sập.

  - Tiện ích chuẩn hoá bằng domain.enums; một httpx.Client dùng chung; không import safety.grounding as grounding (hết vòng phụ thuộc).

  - `get_market_price_stats` không còn mặc định TP.HCM: thiếu city_id thì báo lỗi.

  - `list_housing_skills` không trả đường dẫn máy chủ.

"""



from __future__ import annotations



import json

import logging

import re

import warnings

from typing import Any, Optional



from langchain_core.tools import tool



from domain.budget import relax_budget

from domain.enums import normalize_amenities

from tools.location_service import admin_key, exact_matches, resolve_admin

from domain.schemas import format_vnd_million

from skills.skills_discovery import discover_housing_skills, get_skill

from tools import http

from tools.http import API_BASE, request



logger = logging.getLogger(__name__)



MAX_LIMIT = 20

_LISTING_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

_ADMIN_MSG = ("'{q}' là đơn vị hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã), không trả về toạ độ (lat, lon) theo thiết kế. "

              "Hãy dùng tool get_location_hierarchy để tra cứu ID hành chính (city_id, district_id, ward_id).")

_NO_DATA = ("Hiện tại cơ sở dữ liệu Homigo chưa có dữ liệu {what}. Không dùng geocode_location, không gọi search_rooms và không cần kích hoạt "

            "Human-in-the-Loop. Hãy thông báo tự nhiên cho người dùng và gợi ý các khu vực đang được hỗ trợ.")



# --- tương thích mã cũ -------------------------------------------------------

_unwrap_response = http.unwrap_response





class _Borrowed:

    """`with _client() as c:` kiểu cũ vẫn chạy nhưng KHÔNG đóng client dùng chung."""

    def __enter__(self):

        return http.get_client()



    def __exit__(self, *exc):

        return False





def _client() -> _Borrowed:

    return _Borrowed()





def set_turn_query_context(*a: Any, **k: Any) -> None:

    warnings.warn("set_turn_query_context không còn tác dụng (đã bỏ ngữ cảnh ẩn)", DeprecationWarning, stacklevel=2)





def clear_turn_query_context() -> None:

    return None





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





def _ranked(level: str, name: str, **scope: Any) -> tuple[list[dict[str, Any]], str]:

    """(hàng, 'exact'|'partial'|'none'): khớp chính xác đứng riêng; không có thì trả mọi kết quả server (agent tự chọn)."""

    from tools.location_service import search_term



    rows = admin_lookup(level, search_term(name), **{k: v for k, v in scope.items() if v is not None})

    exact = exact_matches(rows, name)

    return (exact, "exact") if exact else (rows, "partial" if rows else "none")





# =============================================================================

# Định vị điểm

# =============================================================================

def expand_location_with_llm(query: str, hint: Optional[str] = None) -> str:

    """Đường dự phòng khi /geocode 404: nhờ LLM đổi viết tắt/tên lóng thành tên đầy đủ. Lỗi -> giữ nguyên."""

    try:

        from core.llm import get_llm



        model = get_llm("fast")

        if model is None:

            return query

        where = f" tại khu vực {hint}" if hint else " tại Việt Nam"

        res = model.invoke([("system", "Bạn chuẩn hoá địa danh bản đồ Việt Nam. Chỉ trả về MỘT dòng: tên địa điểm đầy đủ kèm quận/thành phố, không giải thích."),

                            ("human", f"Chuẩn hoá để tra OpenStreetMap{where}: \"{query}\"")])

        text = getattr(res, "content", res)

        expanded = str(text).strip().strip("\"'")

        if 3 < len(expanded) < 120 and not expanded.lower().startswith(("tôi", "xin lỗi")):

            return expanded

    except Exception:

        logger.debug("expand_location_with_llm lỗi", exc_info=True)

    return query





def geocode_point(query: str, hint: Optional[str] = None) -> Optional[dict[str, float]]:

    """Hàm lõi: tên địa điểm cụ thể -> {"lat","lng"} hoặc None. KHÔNG kiểm tra hành chính (caller đã biết là địa điểm cụ thể)."""

    q = (query or "").strip()

    if not q:

        return None

    attempts = [(q, hint)]

    tried: set[tuple[str, Optional[str]]] = set()

    while attempts:

        text, h = attempts.pop(0)

        if (text, h) in tried:

            continue

        tried.add((text, h))

        res = request("GET", "/geocode", params={"q": text, **({"hint": h} if h else {})})

        data = res.get("data")

        if res.get("ok") and isinstance(data, dict) and data.get("lat") is not None:

            lng = data.get("lon", data.get("lng"))

            if lng is not None:

                return {"lat": float(data["lat"]), "lng": float(lng)}

        if res.get("status") == 404 and len(tried) == 1:           # lần đầu 404: thử mở rộng bằng LLM, rồi bỏ hint

            expanded = expand_location_with_llm(q, hint)

            if expanded != q:

                attempts.append((expanded, hint))

                if hint:

                    attempts.append((expanded, None))

    return None





@tool

def geocode_location(query: str, hint: Optional[str] = None) -> str:

    """Chuyển đổi tên ĐỊA ĐIỂM CỤ THỂ (trường đại học, ký túc xá, toà nhà, chợ, bệnh viện, tên đường, địa chỉ cụ thể) thành toạ độ (lat, lng).

    LƯU Ý QUAN TRỌNG: TUYỆT ĐỐI KHÔNG dùng tool này cho tên Tỉnh/Thành phố, Quận/Huyện, Phường/Xã (ví dụ: 'Quảng Ngãi', 'TP. Thủ Đức', 'Quận 1', 'Phường Linh Trung'). Với đơn vị hành chính, bắt buộc phải dùng `get_location_hierarchy`.



    Args:

        query: Tên địa điểm cụ thể cần tìm (ví dụ: 'Trường Đại học Công nghệ Thông tin', 'Ký túc xá khu B', 'Đường D2 Bình Thạnh').

        hint: Gợi ý tỉnh/thành phố để thu hẹp tìm kiếm nếu có trong ngữ cảnh.



    Returns:

        JSON string chứa {lat, lon, formatted_address} hoặc thông báo lỗi nếu không tìm thấy / là đơn vị hành chính.

    """

    q = (query or "").strip()

    if not q:

        return dump({"ok": False, "error": "Thiếu tên địa điểm."})

    if resolve_admin(q, admin_lookup, hint).kind in ("admin", "ambiguous"):       # khớp tên chính xác với DB hành chính, không đoán bằng LLM

        return dump({"ok": False, "is_administrative": True, "error": _ADMIN_MSG.format(q=query)})

    point = geocode_point(q, hint)

    if point is None:

        return dump({"ok": False, "error": f"Không tìm thấy toạ độ cho '{query}'. Hãy thử nhập cụ thể hơn hoặc hỏi lại người dùng."})

    return dump({"ok": True, "data": {"lat": point["lat"], "lon": point["lng"]}})





@tool

def get_location_hierarchy(

    city_name: Optional[str] = None,

    district_name: Optional[str] = None,

    ward_name: Optional[str] = None,

    city_id: Optional[int] = None,

    district_id: Optional[int] = None,

) -> str:

    """Tra cứu ID của Tỉnh/Thành phố (city_id), Quận/Huyện (district_id), Phường/Xã (ward_id) từ cơ sở dữ liệu.

    BẮT BUỘC dùng khi người dùng tìm kiếm theo khu vực hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã - ví dụ: 'tìm phòng ở Quảng Ngãi', 'tìm phòng ở Linh Xuân', 'tìm phòng ở Quận 1', 'TP. Thủ Đức'). Không trả về lat/lon.



    Args:

        city_name: Tên tỉnh/thành phố để tìm kiếm (ví dụ 'Hồ Chí Minh', 'Đà Nẵng', 'Quảng Ngãi').

        district_name: Tên quận/huyện/thành phố trực thuộc để tìm kiếm (ví dụ 'Thủ Đức', 'Bình Thạnh', 'Quận 1').

        ward_name: Tên phường/xã để tìm kiếm (ví dụ 'Linh Trung', 'Linh Xuân').

        city_id: ID thành phố (nếu đã biết, dùng để lọc quận chính xác).

        district_id: ID quận/huyện (nếu đã biết, dùng để lọc phường chính xác).



    Returns:

        JSON danh sách địa danh khớp kèm ID (city_id, district_id, ward_id); `match` = 'exact' (khớp tên chính xác) hoặc 'partial'.

    """

    cid, did = city_id, district_id

    if city_name and cid is None and (district_name or ward_name):

        rows, kind = _ranked("city", city_name)

        cid = rows[0].get("id") if kind == "exact" and len(rows) == 1 else None

    if district_name and did is None and ward_name:

        rows, kind = _ranked("district", district_name, city_id=cid)

        if kind == "exact" and len(rows) == 1:

            did, cid = rows[0].get("id"), cid or rows[0].get("city_id")



    if ward_name or (district_id is not None and not district_name and not city_name):

        rows, kind = _ranked("ward", ward_name or "", district_id=did)

        if not rows and ward_name:

            return dump({"ok": True, "data": [], "message": _NO_DATA.format(what=f"tại Phường/Xã '{ward_name}'")})

        return dump({"ok": True, "data": rows, "match": kind, "level": "ward"})



    if district_name or (city_id is not None and not city_name):

        rows, kind = _ranked("district", district_name or "", city_id=cid)

        if not rows and district_name:

            return dump({"ok": True, "data": [], "message": _NO_DATA.format(what=f"tại Quận/Huyện '{district_name}'")})

        return dump({"ok": True, "data": rows, "match": kind, "level": "district"})



    rows, kind = _ranked("city", city_name or "")

    if rows or not city_name:

        return dump({"ok": True, "data": rows, "match": kind, "level": "city"})

    drows, dkind = _ranked("district", city_name)         # 'TP. Thủ Đức'/'Dĩ An' nhập nhầm vào city_name nhưng nằm ở bảng quận/huyện

    if drows:

        return dump({"ok": True, "data": drows, "match": dkind, "level": "district",

                     "note": f"'{city_name}' được lưu ở cấp Quận/Huyện/Thành phố trực thuộc (district_id). Hãy dùng district_id (và city_id) này khi gọi search_rooms."})

    return dump({"ok": True, "data": [], "message": _NO_DATA.format(what=f"phòng trọ tại Tỉnh/Thành phố '{city_name}'")})





# =============================================================================

# Tìm phòng / chi tiết / thống kê giá

# =============================================================================

def search_rooms_api(args: dict[str, Any]) -> dict[str, Any]:

    """Hàm lõi: gọi vector-search. args cùng tên với tool. Trả {"ok", "data"|"error", ...}; KHÔNG ném lỗi."""

    lat, lng = args.get("lat"), args.get("lng")

    body: dict[str, Any] = {"query": str(args.get("query") or ""), "limit": max(1, min(int(args.get("limit") or 5), MAX_LIMIT)), "offset": 0}

    if lat is not None:

        body["lat"] = lat

    if lng is not None:

        body["lng"] = lng

    if lat is None and lng is None:            # có toạ độ thì không gửi ID hành chính (tránh xung đột bán kính)

        for k in ("city_id", "district_id", "ward_id"):

            if args.get(k) is not None:

                body[k] = args[k]

    for k in ("room_type", "min_price", "max_price", "min_area", "max_area"):

        if args.get(k) is not None:

            body[k] = getattr(args[k], "value", args[k])

    amenities = [a.value for a in normalize_amenities(args.get("amenities"))]

    if amenities:

        body["amenities"] = sorted(amenities)

    pref_amenities = [a.value for a in normalize_amenities(args.get("preferred_amenities"))]

    if pref_amenities:

        body["preferred_amenities"] = sorted(pref_amenities)

    if args.get("max_distance_km") is not None:

        body["max_distance_km"] = float(args["max_distance_km"])

    if args.get("weights"):

        body["weights"] = args["weights"]



    res = request("POST", "/listings/vector-search", json=body)

    if res.get("ok") and not res.get("data"):

        res["data"] = []

        res.update(_empty_result_hints(args, amenities))

    return res





def _empty_result_hints(args: dict[str, Any], amenities: list[str]) -> dict[str, Any]:

    suggestions: list[str] = []

    if args.get("max_price"):

        suggestions.append(f"nới ngân sách lên khoảng {format_vnd_million(relax_budget(float(args['max_price'])))}")

    if args.get("ward_id") is not None:

        suggestions.append("mở rộng tìm kiếm ra toàn Quận/Huyện thay vì chỉ 1 Phường")

    elif args.get("district_id") is not None or (args.get("lat") is not None and args.get("lng") is not None):

        suggestions.append("mở rộng phạm vi sang các quận/khu vực lân cận")

    if amenities:

        suggestions.append(f"lược bớt một số tiện ích bắt buộc ({', '.join(amenities)})")

    if args.get("min_area"):

        suggestions.append(f"giảm nhẹ yêu cầu diện tích tối thiểu ({float(args['min_area']):g}m²)")

    hint = ", hoặc ".join(suggestions) or "điều chỉnh lại mức giá hoặc mở rộng khu vực tìm kiếm"

    return {"need_human_in_the_loop": True, "context_suggestions": suggestions,

            "message": ("Truy vấn search_rooms trả về 0 phòng phù hợp với bộ lọc hiện tại. "

                        f"Hãy hỏi ý kiến người dùng (Human-in-the-Loop) một cách linh hoạt dựa trên ngữ cảnh: gợi ý {hint}, hoặc giữ nguyên tiêu chí. "

                        "Lưu ý: nếu người dùng đã thử nới lỏng 2 lần liên tiếp mà vẫn rỗng, hãy dừng đề xuất nới lỏng và khuyên đổi khu vực/nhu cầu mới.")}





@tool

def search_rooms(

    query: str,

    lat: Optional[float] = None,

    lng: Optional[float] = None,

    city_id: Optional[int] = None,

    district_id: Optional[int] = None,

    ward_id: Optional[int] = None,

    room_type: Optional[str] = None,

    min_price: Optional[float] = None,

    max_price: Optional[float] = None,

    min_area: Optional[float] = None,

    max_area: Optional[float] = None,

    amenities: Optional[list[str]] = None,

    weights: Optional[dict[str, float]] = None,

    limit: int = 5,

) -> str:

    """Tìm kiếm phòng trọ bằng Vector Search kết hợp Rerank đa tiêu chí từ Backend.



    Hệ thống sẽ lọc theo các ràng buộc cứng (giá, loại phòng, vị trí/toạ độ, diện tích) và tính toán điểm phù hợp

    (match_score) kèm bản giải thích chi tiết (explain_match: điểm giá, an ninh, tiện ích, vị trí, ngữ nghĩa).



    Args:

        query: Câu mô tả nhu cầu bằng ngôn ngữ tự nhiên (ví dụ: 'phòng trọ có gác lửng, yên tĩnh, cho nuôi mèo, giờ giấc tự do').

        lat: Vĩ độ của điểm mốc (lấy từ geocode_location nếu người dùng tìm quanh một địa điểm).

        lng: Kinh độ của điểm mốc.

        city_id: ID thành phố (lấy từ get_location_hierarchy).

        district_id: ID quận/huyện.

        ward_id: ID phường/xã.

        room_type: Mã loại phòng (ROOM, STUDIO, APARTMENT, SLEEPBOX, WHOLE_HOUSE).

        min_price: Giá tối thiểu bằng VNĐ (ví dụ: 1500000).

        max_price: Giá tối đa bằng VNĐ (ví dụ: 3500000).

        min_area: Diện tích tối thiểu (m²).

        max_area: Diện tích tối đa (m²).

        amenities: Danh sách tiện ích yêu cầu theo format AmenityCode (ví dụ: ['aircon', 'mezzanine', 'pet_allowed']).

        weights: Trọng số động tùy chỉnh (e.g. {'price': 0.35, 'location': 0.35, ...}).

        limit: Số lượng phòng tối đa cần lấy (mặc định 5).



    Returns:

        JSON string chứa danh sách phòng phù hợp nhất kèm match_score và explain_match của từng phòng.

    """

    return dump(search_rooms_api(dict(query=query, lat=lat, lng=lng, city_id=city_id, district_id=district_id, ward_id=ward_id, room_type=room_type,

                                      min_price=min_price, max_price=max_price, min_area=min_area, max_area=max_area, amenities=amenities,

                                      weights=weights, limit=limit)))





def fetch_listing_detail(listing_id: str) -> Optional[dict[str, Any]]:
    """Hàm lõi: Lấy dữ liệu chi tiết của phòng từ backend theo ID. Trả None nếu thất bại."""
    clean = str(listing_id or "").strip()
    if not _LISTING_ID.match(clean):
        return None
    res = request("GET", f"/listings/{clean}")
    if res.get("ok") and isinstance(res.get("data"), dict):
        return res["data"]
    return None


def compact_listing_detail(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Rút gọn dữ liệu chi tiết phòng trọ: loại bỏ ảnh CDN và các trường cồng kềnh,
    giữ lại các trường trọng yếu phục vụ giải đáp Q&A (thú cưng, người ở, chi phí, mô tả...).
    Giảm ~75% token bloat cho LLM context."""
    if not isinstance(raw_data, dict):
        return {}
    keep_keys = (
        "id", "title", "price", "price_million", "deposit", "deposit_million",
        "area_m2", "address", "ward_name", "district_name", "city_name",
        "room_type", "room_type_name", "description", "amenities",
        "stay_max_people", "pet_allowed", "security_score", "surrounding_amenities",
        "electricity_cost", "water_cost", "service_cost", "parking_fee",
        "contact_phone", "contact_name", "notes"
    )
    compact = {k: raw_data[k] for k in keep_keys if k in raw_data and raw_data[k] is not None}
    if "description" in compact and isinstance(compact["description"], str) and len(compact["description"]) > 1500:
        compact["description"] = compact["description"][:1500] + "... (đã rút gọn)"
    return compact


@tool
def get_listing_detail(listing_id: str) -> str:
    """Lấy thông tin chi tiết đầy đủ của một tin đăng phòng trọ cụ thể theo ID.

    Args:
        listing_id: Mã ID của tin đăng (ví dụ: 'nhatot_134860847').

    Returns:
        JSON chi tiết tin đăng (mô tả, thông tin liên hệ, tiền cọc, điểm an ninh, chi phí).
    """
    clean = str(listing_id or "").strip()
    if not _LISTING_ID.match(clean):                        # whitelist: chống Path Traversal sang endpoint khác của backend
        return dump({"ok": False, "error": f"Mã tin đăng '{listing_id}' không hợp lệ."})
    res = request("GET", f"/listings/{clean}")
    if res.get("status") == 404:
        return dump({"ok": False, "error": f"Không tìm thấy tin đăng với mã '{clean}'."})
    if res.get("ok") and isinstance(res.get("data"), dict):
        compacted = compact_listing_detail(res["data"])
        return dump({"ok": True, "data": compacted})
    return dump(res)


def fetch_price_stats(city_id: Optional[int], district_id: Optional[int] = None, room_type_id: Optional[int] = None) -> Optional[dict[str, Any]]:

    """Hàm lõi: `price_stats_general` hoặc None (lỗi/thiếu dữ liệu). Thiếu city_id -> None (không đoán thành phố)."""

    if city_id is None:

        return None

    params = {"city_id": city_id, **({"district_id": district_id} if district_id is not None else {}), **({"room_type_id": room_type_id} if room_type_id is not None else {})}

    res = request("GET", "/listings/price-stats", params=params)

    data = res.get("data") if res.get("ok") else None

    return data.get("price_stats_general") if isinstance(data, dict) else None





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





@tool

def get_market_price_stats(city_id: Optional[int] = None, district_id: Optional[int] = None, room_type_id: Optional[int] = None) -> str:

    """Tra cứu thống kê giá phòng trọ và giá sàn thị trường thực tế từ cơ sở dữ liệu Backend.



    Args:

        city_id: ID Tỉnh/Thành phố (BẮT BUỘC; lấy từ get_location_hierarchy). Không có thì không tra cứu.

        district_id: ID Quận/Huyện nếu muốn tra cứu chi tiết theo quận.

        room_type_id: ID loại phòng (1: ROOM, 2: STUDIO, 3: APARTMENT, 4: SLEEPBOX, 5: WHOLE_HOUSE).



    Returns:

        JSON string chứa price_stats_general (total_listings, average_price_vnd, minimum_price_vnd, maximum_price_vnd)

        và danh sách price_stats_by_area.

    """

    if city_id is None:

        return dump({"ok": False, "error": "Thiếu city_id: hãy tra bằng get_location_hierarchy trước.", "data": None})

    params = {"city_id": city_id, **({"district_id": district_id} if district_id is not None else {}), **({"room_type_id": room_type_id} if room_type_id is not None else {})}

    return dump(request("GET", "/listings/price-stats", params=params))





# =============================================================================

# Kỹ năng

# =============================================================================

def consult_skill(slug: str, query: Optional[str] = None) -> dict[str, Any]:

    """Hàm lõi: nội dung SKILL.md + references/*.md của skill `slug` (tra theo slug trong danh mục đã quét => không Path Traversal)."""

    skill = get_skill(slug)

    if skill is None:

        return {"ok": False, "error": f"Không tìm thấy kỹ năng '{slug}'. Hãy gọi list_housing_skills để xem danh sách kỹ năng khả dụng."}

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
