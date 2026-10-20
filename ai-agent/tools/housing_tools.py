"""Native LangChain tools để tìm kiếm và ra quyết định phòng trọ.
Gọi trực tiếp Backend API qua HTTP mà không cần qua bash hay subprocess.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional
import httpx
from langchain_core.tools import tool

API_BASE = os.environ.get("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
TIMEOUT = float(os.environ.get("SEARCH_ROOM_TIMEOUT", "20.0"))

# Từ khoá nhận diện địa điểm cụ thể (POI, trường học, toà nhà, đường phố, địa chỉ) -> được phép geocode lat/lon
SPECIFIC_POI_KEYWORDS_UNACCENTED = (
    "duong ", "pho ", "hem ", "ngo ", "ngach ", "quoc lo", "ql1", "xa lo", "dai lo",
    "so ", "toa nha", "chung cu", "cao oc", "can ho ", "khu do thi", "kdt ", "vinhomes",
    "truong ", "dai hoc", "dh ", "cao dang", "hoc vien", "ky tuc xa", "ktx",
    "lang dai hoc", "dhqg", "uit", "khtn", "bach khoa", "dhbk", "bku", "nong lam",
    "spkt", "su pham ky thuat", "kinh te luat", "uel", "hutech", "fpt", "rmit",
    "ton duc thang", "van lang", "hong bang", "ngoai thuong", "ftu", "ueh", "y duoc",
    "benh vien", "cho ", "sieu thi", "trung tam thuong mai", "tttm", "vincom", "aeon",
    "big c", "coopmart", "lotte", "gigamall", "landmark", "bitexco", "suoi tien",
    "cong vien", "cau ", "nga tu", "nga ba", "nga nam", "nga sau", "vong xoay",
    "ben xe", "ga ", "san bay", "khu cong nghe", "kcnc", "khu che xuat", "kcx",
    "khu cong nghiep", "kcn", "cong ty", "van phong", "nha tho", "chua ",
)

# Danh mục 63 Tỉnh/Thành phố & các thành phố trực thuộc tỉnh (không dấu)
VN_PROVINCES_UNACCENTED = {
    "an giang", "ba ria", "vung tau", "ba ria vung tau", "ba ria - vung tau",
    "bac giang", "bac kan", "bac lieu", "bac ninh", "ben tre", "binh dinh",
    "binh duong", "binh phuoc", "binh thuan", "ca mau", "can tho", "cao bang",
    "da nang", "dak lak", "dac lac", "dak nong", "dien bien", "dong nai",
    "dong thap", "gia lai", "ha giang", "ha nam", "ha noi", "ha tinh",
    "hai duong", "hai phong", "hau giang", "hoa binh", "hung yen", "khanh hoa",
    "kien giang", "kon tum", "lai chau", "lam dong", "lang son", "lao cai",
    "long an", "nam dinh", "nghe an", "ninh binh", "ninh thuan", "phu tho",
    "phu yen", "quang binh", "quang nam", "quang ngai", "quang ninh",
    "quang tri", "soc trang", "son la", "tay ninh", "thai binh", "thai nguyen",
    "thanh hoa", "thua thien hue", "hue", "tien giang", "ho chi minh",
    "tphcm", "tp hcm", "hcm", "sai gon", "saigon", "tra vinh", "tuyen quang",
    "vinh long", "vinh phuc", "yen bai",
    "da lat", "nha trang", "buon ma thuot", "quy nhon", "ha long", "bien hoa",
    "vinh", "pleiku", "phan thiet", "phan rang", "cam ranh", "hoi an", "tam ky",
    "my tho", "long xuyen", "chau doc", "rach gia", "phu quoc", "vi thanh",
    "cao lanh", "sa dec", "tan an", "dong xoai", "thu dau mot", "di an",
    "thuan an", "ben cat", "tan uyen", "long khanh", "bao loc", "gia nghia",
    "tuy hoa", "dong ha", "dong hoi", "sam son", "hoa lu", "phu ly", "chi linh",
    "tu son", "viet tri", "vinh yen", "phuc yen", "song cong", "pho yen",
    "uong bi", "cam pha", "mong cai", "dien bien phu",
}

# Danh mục Quận/Huyện, Phường/Xã phổ biến (không dấu)
VN_ADMIN_AREAS_UNACCENTED = {
    "thu duc", "binh thanh", "go vap", "tan binh", "tan phu", "phu nhuan",
    "binh tan", "cu chi", "hoc mon", "binh chanh", "nha be", "can gio",
    "quan 1", "quan 2", "quan 3", "quan 4", "quan 5", "quan 6", "quan 7",
    "quan 8", "quan 9", "quan 10", "quan 11", "quan 12",
    "ba dinh", "hoan kiem", "tay ho", "long bien", "cau giay", "dong da",
    "hai ba trung", "hoang mai", "thanh xuan", "ha dong", "nam tu liem",
    "bac tu liem", "gia lam", "dong anh", "thanh tri", "soc son", "hoa lac",
    "hai chau", "thanh khe", "son tra", "ngu hanh son", "lien chieu", "cam le",
    "hoa vang", "ninh kieu", "binh thuy", "cai rang", "o mon", "thot not",
    "linh trung", "linh xuan", "linh chieu", "linh tay", "linh dong",
    "binh tho", "truong tho", "hiep binh chanh", "hiep binh phuoc",
    "tam binh", "tam phu", "tang nhon phu", "tang nhon phu a", "tang nhon phu b",
    "phuoc long", "phuoc long a", "phuoc long b", "long thanh my",
    "long binh", "long phuoc", "long truong", "phu huu", "thao dien", "an phu",
    "an khanh", "binh an", "binh trung dong", "binh trung tay", "cat lai",
    "thanh my loi", "thu thiem", "dong hoa", "binh thang", "an binh",
    "tan dong hiep", "tan quy", "tan phong", "tan thuan dong", "tan thuan tay",
    "tan kieng", "tan hung", "phu my", "binh thuan",
}

ADMIN_PREFIX_PATTERN = re.compile(
    r"^(?:tinh|thanh pho|tp\.?|quan|q\.?|huyen|h\.?|thi xa|tx\.?|phuong|p\.?|xa|thi tran|tt\.?)\s+(.+)$",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    """Chuyển chuỗi tiếng Việt có dấu sang không dấu viết thường để đối sánh bền vững."""
    text = unicodedata.normalize("NFC", text or "").strip().lower()
    text = text.replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _is_administrative_location_query(query: str) -> bool:
    """Kiểm tra xem truy vấn vị trí có phải chỉ là đơn vị hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã) hay không.
    Nếu là địa điểm cụ thể (trường học, toà nhà, tên đường, KTX, chợ...) -> trả về False.
    Nếu chỉ là Tỉnh/Thành phố, Quận/Huyện, Phường/Xã -> trả về True (không trả về lat/lon).
    """
    if not query or not query.strip():
        return False

    unaccented = _strip_accents(query)
    # Làm sạch các từ dẫn đầu thông thường
    unaccented = re.sub(
        r"^((tim|o|gan|quanh|khu vuc|tai|xung quanh|phong|tro|bat ky dau|dau cung duoc)\s+)+",
        "",
        unaccented,
    ).strip()
    unaccented = re.sub(r"\s+(bat ky dau|dau cung duoc|gia re|phong tro|tro).*$", "", unaccented).strip()
    if not unaccented:
        return False

    # Nếu chứa từ khoá địa điểm cụ thể (trường học, tên đường, KTX, toà nhà, chợ...) -> KHÔNG phải đơn vị hành chính thuần tuý
    padded = f" {unaccented} "
    for kw in SPECIFIC_POI_KEYWORDS_UNACCENTED:
        if f" {kw.strip()} " in padded or unaccented.startswith(kw):
            return False

    # Tách theo dấu phẩy / gạch ngang (ví dụ: "Linh Trung, Thủ Đức, TP.HCM")
    parts = [p.strip() for p in re.split(r"[,;-]+", unaccented) if p.strip()]
    if not parts:
        return False

    for part in parts:
        if part in ("viet nam", "vn"):
            continue
        if part in VN_PROVINCES_UNACCENTED or part in VN_ADMIN_AREAS_UNACCENTED:
            continue
        m = ADMIN_PREFIX_PATTERN.match(part)
        if m:
            remainder = m.group(1).strip()
            rem_padded = f" {remainder} "
            # Nếu sau tiền tố hành chính không chứa từ khoá POI cụ thể thì đây là đơn vị hành chính
            if remainder and not any(f" {kw.strip()} " in rem_padded or remainder.startswith(kw) for kw in SPECIFIC_POI_KEYWORDS_UNACCENTED):
                continue
        return False

    return True


def _normalize_admin_search_term(raw_name: str) -> str:
    """Chuẩn hoá tên đơn vị hành chính trước khi truy vấn ILIKE trong cơ sở dữ liệu."""
    cleaned = unicodedata.normalize("NFC", raw_name or "").strip()
    unacc = _strip_accents(cleaned)

    if unacc in ("tphcm", "tp.hcm", "tp hcm", "hcm", "sai gon", "saigon", "tp. ho chi minh", "tp ho chi minh", "thanh pho ho chi minh"):
        return "Hồ Chí Minh"
    if unacc in ("hn", "tp ha noi", "tp. ha noi", "thanh pho ha noi"):
        return "Hà Nội"
    if unacc in ("dn", "tp da nang", "tp. da nang", "thanh pho da nang"):
        return "Đà Nẵng"
    if unacc == "quang ngai":
        return "Quảng Ngãi"

    # Quận / Phường đánh số (ví dụ: Q1, Q.1, Quận 1, P.25)
    m_q = re.match(r"^(?:quận|quan|q\.?)\s*(\d+)$", cleaned, flags=re.IGNORECASE)
    if m_q:
        return f"Quận {m_q.group(1)}"
    m_p = re.match(r"^(?:phường|phuong|p\.?)\s*(\d+)$", cleaned, flags=re.IGNORECASE)
    if m_p:
        return f"Phường {m_p.group(1)}"

    # Lược bỏ tiền tố hành chính cho địa danh có tên chữ để khớp linh hoạt với cả "Tp ...", "Thành phố ...", "Quận ...", "Phường ..."
    stripped = re.sub(
        r"^(?:tỉnh|thành phố|tp\.?|quận|q\.?|huyện|h\.?|thị xã|tx\.?|phường|p\.?|xã|thị trấn|tt\.?)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or cleaned


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=TIMEOUT, follow_redirects=True)


def _unwrap_response(resp: httpx.Response) -> dict:
    if resp.status_code == 404:
        return {"ok": False, "error": "Không tìm thấy dữ liệu (HTTP 404)"}
    try:
        data = resp.json()
    except Exception:
        preview = resp.text[:200].strip() if resp.text else f"status {resp.status_code}"
        return {"ok": False, "error": f"Phản hồi không phải JSON ({preview})"}

    if isinstance(data, dict) and "data" in data and "success" in data:
        if not data.get("success", False):
            return {"ok": False, "error": data.get("message", "API trả về lỗi")}
        return {"ok": True, "data": data["data"]}
    return {"ok": True, "data": data}


import contextvars
from extractor import AMENITY_CATALOG, CANONICAL_AMENITIES, _fallback_extract

_TURN_CONTEXT_VAR: contextvars.ContextVar[Optional[dict[str, Any]]] = contextvars.ContextVar(
    "_TURN_CONTEXT_VAR", default=None
)
_FALLBACK_TURN_CONTEXT: Optional[dict[str, Any]] = None


def set_turn_query_context(user_query: str, session_text: Optional[str] = None) -> None:
    """Thiết lập ngữ cảnh truy vấn gốc của người dùng cho lượt gọi Agent hiện tại,
    đảm bảo search_rooms + rerank luôn nhận bộ tham số chuẩn hóa đồng nhất giữa Streamlit và Frontend.
    """
    global _FALLBACK_TURN_CONTEXT
    ctx = {
        "user_query": (user_query or "").strip(),
        "session_text": (session_text or user_query or "").strip(),
        "lat": None,
        "lng": None,
        "city_id": None,
        "district_id": None,
        "ward_id": None,
        "room_type": None,
        "room_type_id": None,
    }
    _TURN_CONTEXT_VAR.set(ctx)
    _FALLBACK_TURN_CONTEXT = ctx


def clear_turn_query_context() -> None:
    """Xoá ngữ cảnh truy vấn sau khi kết thúc lượt gọi Agent."""
    global _FALLBACK_TURN_CONTEXT
    _TURN_CONTEXT_VAR.set(None)
    _FALLBACK_TURN_CONTEXT = None


def _get_turn_context() -> Optional[dict[str, Any]]:
    return _TURN_CONTEXT_VAR.get() or _FALLBACK_TURN_CONTEXT


def _normalize_amenity_list(raw_amenities: Optional[list[str]]) -> list[str]:
    """Lọc danh sách tiện ích, đảm bảo đúng định dạng canonical AmenityCode của hệ thống."""
    if not raw_amenities:
        return []
    out: list[str] = []
    for item in raw_amenities:
        if not item:
            continue
        clean = item.strip().lower()
        if clean in CANONICAL_AMENITIES and clean not in out:
            out.append(clean)
    return sorted(out)


@tool
def geocode_location(query: str, hint: str = "Hồ Chí Minh") -> str:
    """Chuyển đổi tên ĐỊA ĐIỂM CỤ THỂ (trường đại học, ký túc xá, toà nhà, chợ, bệnh viện, tên đường, địa chỉ cụ thể) thành toạ độ (lat, lng).
    LƯU Ý QUAN TRỌNG: TUYỆT ĐỐI KHÔNG dùng tool này cho tên Tỉnh/Thành phố, Quận/Huyện, Phường/Xã (ví dụ: 'Quảng Ngãi', 'TP. Thủ Đức', 'Quận 1', 'Phường Linh Trung'). Với đơn vị hành chính, bắt buộc phải dùng `get_location_hierarchy`.

    Args:
        query: Tên địa điểm cụ thể cần tìm (ví dụ: 'Trường Đại học Công nghệ Thông tin', 'Ký túc xá khu B', 'Đường D2 Bình Thạnh').
        hint: Gợi ý tỉnh/thành phố để thu hẹp tìm kiếm (mặc định 'Hồ Chí Minh').

    Returns:
        JSON string chứa {lat, lon, formatted_address} hoặc thông báo lỗi nếu không tìm thấy / là đơn vị hành chính.
    """
    if _is_administrative_location_query(query):
        return json.dumps({
            "ok": False,
            "is_administrative": True,
            "error": (
                f"'{query}' là đơn vị hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã), "
                "không trả về toạ độ (lat, lon) theo thiết kế. "
                "Hãy dùng tool get_location_hierarchy để tra cứu ID hành chính (city_id, district_id, ward_id)."
            ),
        }, ensure_ascii=False)

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
            ctx = _get_turn_context()
            if ctx is not None and unwrapped.get("ok") and isinstance(unwrapped.get("data"), dict):
                gdata = unwrapped["data"]
                if gdata.get("lat") is not None and gdata.get("lon") is not None:
                    ctx["lat"] = float(gdata["lat"])
                    ctx["lng"] = float(gdata["lon"])
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
    """Tra cứu ID của Tỉnh/Thành phố (city_id), Quận/Huyện (district_id), Phường/Xã (ward_id) từ cơ sở dữ liệu.
    BẮT BUỘC dùng khi người dùng tìm kiếm theo khu vực hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã - ví dụ: 'tìm phòng ở Quảng Ngãi', 'tìm phòng ở Linh Xuân', 'tìm phòng ở Quận 1', 'TP. Thủ Đức'). Không trả về lat/lon.

    Args:
        city_name: Tên tỉnh/thành phố để tìm kiếm (ví dụ 'Hồ Chí Minh', 'Đà Nẵng', 'Quảng Ngãi').
        district_name: Tên quận/huyện/thành phố trực thuộc để tìm kiếm (ví dụ 'Thủ Đức', 'Bình Thạnh', 'Quận 1').
        ward_name: Tên phường/xã để tìm kiếm (ví dụ 'Linh Trung', 'Linh Xuân').
        city_id: ID thành phố (nếu đã biết, dùng để lọc quận chính xác).
        district_id: ID quận/huyện (nếu đã biết, dùng để lọc phường chính xác).

    Returns:
        JSON danh sách các địa danh hành chính khớp kèm ID tương ứng (city_id, district_id, ward_id).
    """
    try:
        with _client() as client:
            resolved_city_id = city_id
            resolved_district_id = district_id
            ctx = _get_turn_context()

            # Nếu có truyền city_name và đồng thời có district_name/ward_name, giải quyết city_id trước để lọc chuẩn
            if city_name and resolved_city_id is None and (district_name or ward_name):
                norm_city = _normalize_admin_search_term(city_name)
                c_resp = _unwrap_response(client.get("/locations/cities", params={"search": norm_city}))
                c_list = c_resp.get("data") if isinstance(c_resp, dict) else None
                if isinstance(c_list, list) and len(c_list) > 0:
                    resolved_city_id = c_list[0].get("id")

            # Nếu có truyền district_name và đồng thời có ward_name, giải quyết district_id trước để lọc chuẩn
            if district_name and resolved_district_id is None and ward_name:
                norm_dist = _normalize_admin_search_term(district_name)
                d_params: dict[str, Any] = {"search": norm_dist}
                if resolved_city_id is not None:
                    d_params["city_id"] = resolved_city_id
                d_resp = _unwrap_response(client.get("/locations/districts", params=d_params))
                d_list = d_resp.get("data") if isinstance(d_resp, dict) else None
                if isinstance(d_list, list) and len(d_list) > 0:
                    resolved_district_id = d_list[0].get("id")
                    if resolved_city_id is None:
                        resolved_city_id = d_list[0].get("city_id")

            # 1. Tra cứu phường nếu có yêu cầu
            if ward_name or (district_id is not None and not district_name and not city_name):
                params: dict[str, Any] = {}
                if resolved_district_id is not None:
                    params["district_id"] = resolved_district_id
                if ward_name:
                    params["search"] = _normalize_admin_search_term(ward_name)
                resp = client.get("/locations/wards", params=params)
                unwrapped = _unwrap_response(resp)
                if unwrapped.get("ok") and unwrapped.get("data") and ctx is not None and ward_name:
                    w0 = unwrapped["data"][0]
                    ctx["ward_id"] = w0.get("id")
                    ctx["district_id"] = w0.get("district_id") or resolved_district_id
                    if resolved_city_id is not None:
                        ctx["city_id"] = resolved_city_id
                if unwrapped.get("ok") and not unwrapped.get("data") and ward_name:
                    unwrapped["message"] = (
                        f"Hiện tại cơ sở dữ liệu Homigo chưa có dữ liệu tại Phường/Xã '{ward_name}'. "
                        "Không dùng geocode_location, không gọi search_rooms và không cần kích hoạt Human-in-the-Loop. "
                        "Hãy thông báo tự nhiên cho người dùng và gợi ý các khu vực lân cận đang có dữ liệu."
                    )
                return json.dumps(unwrapped, ensure_ascii=False)

            # 2. Tra cứu quận/huyện nếu có yêu cầu
            if district_name or (city_id is not None and not city_name):
                params = {}
                if resolved_city_id is not None:
                    params["city_id"] = resolved_city_id
                if district_name:
                    params["search"] = _normalize_admin_search_term(district_name)
                resp = client.get("/locations/districts", params=params)
                unwrapped = _unwrap_response(resp)
                if unwrapped.get("ok") and unwrapped.get("data") and ctx is not None and district_name:
                    d0 = unwrapped["data"][0]
                    ctx["district_id"] = d0.get("id")
                    ctx["city_id"] = d0.get("city_id") or resolved_city_id
                if unwrapped.get("ok") and not unwrapped.get("data") and district_name:
                    unwrapped["message"] = (
                        f"Hiện tại cơ sở dữ liệu Homigo chưa có dữ liệu tại Quận/Huyện '{district_name}'. "
                        "Không dùng geocode_location, không gọi search_rooms và không cần kích hoạt Human-in-the-Loop. "
                        "Hãy thông báo tự nhiên cho người dùng và gợi ý các khu vực đang được hỗ trợ."
                    )
                return json.dumps(unwrapped, ensure_ascii=False)

            # 3. Tra cứu tỉnh/thành phố
            params = {}
            norm_city = _normalize_admin_search_term(city_name) if city_name else None
            if norm_city:
                params["search"] = norm_city
            resp = client.get("/locations/cities", params=params)
            unwrapped = _unwrap_response(resp)
            if unwrapped.get("ok") and unwrapped.get("data") and ctx is not None and norm_city:
                c0 = unwrapped["data"][0]
                ctx["city_id"] = c0.get("id")

            # Fallback: Nếu người dùng nhập 'TP. Thủ Đức' hoặc 'Dĩ An' vào city_name (thực tế nằm ở bảng districts)
            if unwrapped.get("ok") and not unwrapped.get("data") and norm_city:
                d_resp = _unwrap_response(client.get("/locations/districts", params={"search": norm_city}))
                if d_resp.get("ok") and d_resp.get("data"):
                    if ctx is not None:
                        d0 = d_resp["data"][0]
                        ctx["district_id"] = d0.get("id")
                        ctx["city_id"] = d0.get("city_id")
                    d_resp["level"] = "district"
                    d_resp["note"] = (
                        f"'{city_name}' được lưu ở cấp Quận/Huyện/Thành phố trực thuộc (district_id) trong cơ sở dữ liệu. "
                        "Hãy dùng district_id (và city_id) này khi gọi search_rooms."
                    )
                    return json.dumps(d_resp, ensure_ascii=False)

                unwrapped["message"] = (
                    f"Hiện tại cơ sở dữ liệu Homigo chưa có dữ liệu phòng trọ tại Tỉnh/Thành phố '{city_name}'. "
                    "Tuyệt đối KHÔNG gọi geocode_location, KHÔNG gọi search_rooms và KHÔNG kích hoạt Human-in-the-Loop. "
                    "Hãy thông báo lịch sự cho người dùng biết khu vực này chưa có dữ liệu và gợi ý các tỉnh/thành phố đang có trên hệ thống (như TP.HCM, Bình Dương, Đà Nẵng, Hà Nội, Cần Thơ...)."
                )
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
    room_type: Optional[str] = None,
    room_type_id: Optional[int] = None,
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
        room_type_id: ID loại phòng (1: ROOM, 2: STUDIO, 3: APARTMENT, 4: SLEEPBOX, 5: WHOLE_HOUSE).
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
    ctx = _get_turn_context()
    if ctx is not None and ctx.get("user_query"):
        # Đồng nhất 100% các tham số đầu vào của Vector Search + Rerank giữa Streamlit và Frontend
        query = ctx["user_query"]
        limit = 5
        weights = ctx.get("weights")

        user_q_low = ctx["user_query"].lower()
        if "lược bớt" in user_q_low or user_q_low.startswith("🪄"):
            amenities = []
        else:
            ext_session = _fallback_extract(ctx.get("session_text") or ctx["user_query"])
            amenities = sorted(set(ext_session.amenities)) if ext_session.amenities else (_normalize_amenity_list(amenities) if amenities else [])

        if max_price is None or min_price is None or room_type is None:
            ext_turn = _fallback_extract(ctx["user_query"])
            if max_price is None and ext_turn.max_price is not None:
                max_price = ext_turn.max_price
            if min_price is None and ext_turn.min_price is not None:
                min_price = ext_turn.min_price
            if room_type is None and ext_turn.room_type is not None:
                room_type = ext_turn.room_type

        if ctx.get("lat") is not None and ctx.get("lng") is not None:
            lat = ctx["lat"]
            lng = ctx["lng"]
            city_id = None
            district_id = None
            ward_id = None
        else:
            if ward_id is None and ctx.get("ward_id") is not None:
                ward_id = ctx["ward_id"]
            if district_id is None and ctx.get("district_id") is not None:
                district_id = ctx["district_id"]
            if city_id is None and ctx.get("city_id") is not None:
                city_id = ctx["city_id"]
    else:
        amenities = _normalize_amenity_list(amenities) if amenities else None

    # Toàn bộ tham số được gửi qua JSON Body (không dùng query params)
    body: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "offset": 0,
    }
    if lat is not None:
        body["lat"] = lat
    if lng is not None:
        body["lng"] = lng
    if city_id is not None:
        body["city_id"] = city_id
    if district_id is not None:
        body["district_id"] = district_id
    if ward_id is not None:
        body["ward_id"] = ward_id
    if room_type is not None:
        body["room_type"] = room_type
    if room_type_id is not None:
        body["room_type_id"] = room_type_id
    if min_price is not None:
        body["min_price"] = min_price
    if max_price is not None:
        body["max_price"] = max_price
    if min_area is not None:
        body["min_area"] = min_area
    if max_area is not None:
        body["max_area"] = max_area
    if amenities:
        body["amenities"] = amenities
    if weights:
        body["weights"] = weights

    try:
        with _client() as client:
            resp = client.post("/listings/vector-search", json=body)
            if resp.is_error:
                return json.dumps({
                    "ok": False,
                    "error": f"HTTP {resp.status_code}: {resp.text}"
                }, ensure_ascii=False)
            unwrapped = _unwrap_response(resp)
            if unwrapped.get("ok") and not unwrapped.get("data"):
                suggestions = []
                if max_price and max_price > 0:
                    from grounding import calculate_smart_budget_proposal
                    from schemas import UserPreferenceState

                    temp_pref = UserPreferenceState(max_price=max_price)
                    smart = calculate_smart_budget_proposal(temp_pref)
                    if smart.get("is_market_gap"):
                        suggestions.append(f"nới ngân sách lên theo giá sàn thị trường (~{smart['proposed_budget_str']})")
                    else:
                        prop_val = (max_price * 1.15) / 1_000_000
                        prop_str = f"{prop_val:.2f} triệu/tháng".replace(".00", "")
                        suggestions.append(f"nới ngân sách thêm khoảng 15% (lên ~{prop_str})")
                if ward_id is not None:
                    suggestions.append("mở rộng tìm kiếm ra toàn Quận/Huyện thay vì chỉ 1 Phường")
                elif district_id is not None or (lat is not None and lng is not None):
                    suggestions.append("mở rộng phạm vi sang các quận/khu vực lân cận")
                if amenities and len(amenities) > 0:
                    suggestions.append(f"lược bớt một số tiện ích bắt buộc ({', '.join(amenities)})")
                if min_area and min_area > 0:
                    suggestions.append(f"giảm nhẹ yêu cầu diện tích tối thiểu ({min_area:g}m²)")

                hint_str = ", hoặc ".join(suggestions) if suggestions else "điều chỉnh lại mức giá hoặc mở rộng khu vực tìm kiếm"
                unwrapped["need_human_in_the_loop"] = True
                unwrapped["context_suggestions"] = suggestions
                unwrapped["message"] = (
                    "Truy vấn search_rooms trả về 0 phòng phù hợp với bộ lọc hiện tại. "
                    f"Hãy hỏi ý kiến người dùng (Human-in-the-Loop) một cách linh hoạt dựa trên ngữ cảnh: gợi ý {hint_str}, "
                    "hoặc giữ nguyên tiêu chí. Lưu ý: nếu trong hội thoại người dùng đã thử nới lỏng 2 lần liên tiếp mà vẫn rỗng, "
                    "hãy dừng đề xuất nới lỏng và khuyên người dùng đổi khu vực/nhu cầu mới."
                )
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


@tool
def list_housing_skills() -> str:
    """Liệt kê danh sách các Kỹ năng chuyên sâu (Housing Skills) hiện có trong hệ thống Homigo.
    Hệ thống hỗ trợ nạp thêm kỹ năng động bất cứ lúc nào (ví dụ: 'rental-contract-advisor').

    Returns:
        JSON danh sách các kỹ năng kèm mô tả công dụng.
    """
    base_dirs = [
        Path(__file__).resolve().parent.parent / "skills",
        Path(__file__).resolve().parent.parent / "workspace" / "skills",
        Path(__file__).resolve().parent.parent / "fixtures" / "skills",
    ]

    seen = set()
    available = []
    for b in base_dirs:
        if b.exists():
            for skill_path in sorted(b.glob("*/SKILL.md")):
                name = skill_path.parent.name
                if name in seen:
                    continue
                seen.add(name)
                desc = ""
                try:
                    content = skill_path.read_text(encoding="utf-8")
                    for line in content.splitlines():
                        if line.startswith("description:"):
                            desc = line.replace("description:", "").strip()
                            break
                except Exception:
                    pass
                available.append({
                    "name": name,
                    "description": desc,
                    "path": f"skills/{name}/SKILL.md",
                })

    return json.dumps({"ok": True, "skills": available}, ensure_ascii=False)


@tool
def consult_housing_skill(
    skill_name: str,
    query: Optional[str] = None,
) -> str:
    """Tra cứu và tham vấn tài liệu hướng dẫn chuyên sâu từ một Housing Skill (ví dụ: 'rental-contract-advisor').
    Dùng khi người dùng cần hỗ trợ về pháp lý, kiểm tra hợp đồng thuê trọ, bẫy tiền cọc hoặc các kỹ năng khác.

    Args:
        skill_name: Tên của kỹ năng muốn tham vấn (ví dụ: 'rental-contract-advisor').
        query: Câu hỏi hoặc nội dung điều khoản cụ thể cần tư vấn.

    Returns:
        JSON chứa toàn bộ nội dung hướng dẫn, checklist và lưu ý từ kỹ năng tương ứng.
    """
    base_dirs = [
        Path(__file__).resolve().parent.parent / "skills",
        Path(__file__).resolve().parent.parent / "workspace" / "skills",
        Path(__file__).resolve().parent.parent / "fixtures" / "skills",
    ]

    skill_folder = None
    for b in base_dirs:
        cand = b / skill_name
        if cand.is_dir():
            skill_folder = cand
            break

    if not skill_folder:
        return json.dumps({
            "ok": False,
            "error": f"Không tìm thấy kỹ năng '{skill_name}'. Hãy gọi list_housing_skills để xem danh sách kỹ năng khả dụng."
        }, ensure_ascii=False)

    try:
        skill_file = skill_folder / "SKILL.md"
        skill_md = skill_file.read_text(encoding="utf-8") if skill_file.exists() else ""
        references = {}
        ref_dir = skill_folder / "references"
        if ref_dir.is_dir():
            for ref_file in ref_dir.glob("*.md"):
                references[ref_file.name] = ref_file.read_text(encoding="utf-8")

        return json.dumps({
            "ok": True,
            "skill_name": skill_name,
            "instructions": skill_md,
            "references": references,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Lỗi đọc nội dung kỹ năng: {str(e)}"}, ensure_ascii=False)

@tool
def get_market_price_stats(
    city_id: int = 79,
    district_id: Optional[int] = None,
    room_type_id: Optional[int] = None,
) -> str:
    """Tra cứu thống kê giá phòng trọ và giá sàn thị trường thực tế từ cơ sở dữ liệu Backend.

    Args:
        city_id: ID Tỉnh/Thành phố (mặc định 79 cho TP.HCM).
        district_id: ID Quận/Huyện nếu muốn tra cứu chi tiết theo quận.
        room_type_id: ID loại phòng (1: ROOM, 2: STUDIO, 3: APARTMENT, 4: SLEEPBOX, 5: WHOLE_HOUSE).

    Returns:
        JSON string chứa price_stats_general (total_listings, average_price_vnd, minimum_price_vnd, maximum_price_vnd)
        và danh sách price_stats_by_area.
    """
    params: dict[str, Any] = {"city_id": city_id}
    if district_id is not None:
        params["district_id"] = district_id
    if room_type_id is not None:
        params["room_type_id"] = room_type_id

    try:
        with _client() as client:
            resp = client.get("/api/v1/listings/price-stats", params=params)
            data = _unwrap_response(resp)
            return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Lỗi khi tra cứu thống kê giá phòng /price-stats: {e}")
        return json.dumps({"ok": False, "error": str(e), "data": None}, ensure_ascii=False)

