"""Phân giải địa danh bằng CODE (không gọi LLM): hành chính -> (city_id, district_id, ward_id); địa điểm cụ thể -> (lat, lng).

NLU đã cho biết địa danh là 'admin' hay 'place' (PreferencePatch.location_kind) nên không cần LLM phân loại mỗi lượt nữa.
Khác bản cũ:
  - Khớp TÊN CHÍNH XÁC sau chuẩn hoá (bỏ dấu, bỏ tiền tố 'Phường/Quận/TP.', alias tphcm/hn/q1...), không lấy `data[0]` mù:
    "Chợ Thủ Đức" không còn bị server-side `search` kéo về quận Thủ Đức.
  - Trùng tên (nhiều 'Phường 1') -> trả `ambiguous` + danh sách ứng viên để HỎI người dùng, không đoán.
  - Thiếu dữ liệu hành chính -> `admin_not_found` (thông báo "chưa có dữ liệu"), không lẫn với "không geocode được".

Hàm thuần: `admin_lookup` và `geocode` được truyền vào (production nối tới HTTP/tool ở graph/deps.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from utils.text import contains_phrase, norm_key, tokens

Kind = Literal["admin", "point", "admin_not_found", "unresolved_point", "ambiguous"]

# admin_lookup(level, name, city_id=None, district_id=None) -> list[{"id", "name", "city_id"?, "district_id"?}]
AdminLookup = Callable[..., list[dict[str, Any]]]
# geocode(query, hint) -> {"lat": float, "lng": float} | {"ambiguous": True, "candidates": list[dict]} | None
Geocode = Callable[[str, Optional[str]], Optional[dict[str, Any]]]

_ALIASES = {
    "tphcm": "ho chi minh", "tp hcm": "ho chi minh", "hcm": "ho chi minh", "sg": "ho chi minh", "sai gon": "ho chi minh", "saigon": "ho chi minh",
    "hn": "ha noi", "dn": "da nang", "bd": "binh duong", "ct": "can tho", "hp": "hai phong", "dna": "dong nai",
    # Ánh xạ các quận cũ của TP.HCM đã sáp nhập vào Thành phố Thủ Đức
    "2": "thu duc", "quan 2": "thu duc", "q2": "thu duc", "q 2": "thu duc",
    "9": "thu duc", "quan 9": "thu duc", "q9": "thu duc", "q 9": "thu duc",
    "tp thu duc": "thu duc", "thanh pho thu duc": "thu duc",
}
_PREFIXES: list[tuple[str, str]] = [   # (tiền tố đã bỏ dấu, cấp gợi ý)
    ("thanh pho ", "city"), ("tinh ", "city"), ("tp. ", "city"), ("tp ", "city"),
    ("thi xa ", "district"), ("quan ", "district"), ("huyen ", "district"), ("q. ", "district"), ("q ", "district"),
    ("thi tran ", "ward"), ("phuong ", "ward"), ("xa ", "ward"), ("p. ", "ward"), ("p ", "ward"),
]
_QN = re.compile(r"^q\.?\s*(\d+)$")
_PN = re.compile(r"^p\.?\s*(\d+)$")
_PLACE_HINTS = re.compile(
    r"\b(?:đh|trường|đại\s*học|học\s*viện|ký\s*túc\s*xá|ktx|bệnh\s*viện|chợ|bến\s*xe|kcn|khu\s*công\s*nghiệp|chung\s*cư|tòa\s*nhà|toà\s*nhà|công\s*viên)\b",
    re.IGNORECASE,
)


_ALIAS_DISPLAY = {   # alias -> tên chính thức CÓ DẤU, dùng làm từ khoá gửi lên server
    "ho chi minh": "Hồ Chí Minh", "ha noi": "Hà Nội", "da nang": "Đà Nẵng", "binh duong": "Bình Dương",
    "can tho": "Cần Thơ", "hai phong": "Hải Phòng", "dong nai": "Đồng Nai",
    "thu duc": "Thủ Đức",
}

_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _dedot(name: Optional[str]) -> str:
    s = _PAREN_RE.sub(" ", name or "")
    return " ".join(s.replace(".", " ").split())


def admin_key(name: Optional[str]) -> str:
    """'TP.HCM' / 'tphcm' / 'Hồ Chí Minh' -> 'ho chi minh'; 'Quận 7' / 'q7' -> '7'; 'Phường Linh Trung' -> 'linh trung'."""
    k = norm_key(_dedot(name))
    if m := _QN.match(k):
        q = m.group(1)
        return _ALIASES.get(q, q)
    if m := _PN.match(k):
        return m.group(1)
    k = _ALIASES.get(k, k)
    for pfx, _lvl in _PREFIXES:
        if k.startswith(pfx):
            k = k[len(pfx):].strip()
            break
    return _ALIASES.get(k, k)


def level_hint(name: Optional[str]) -> Optional[str]:
    """Tiền tố cho biết cấp: 'Quận 7' -> 'district', 'Phường 1' -> 'ward', 'Tỉnh X' -> 'city'."""
    k = norm_key(_dedot(name))
    if _QN.match(k):
        return "district"
    if _PN.match(k):
        return "ward"
    for pfx, lvl in _PREFIXES:
        if k.startswith(pfx):
            return lvl
    return None


def search_term(name: Optional[str]) -> str:
    """Từ khoá gửi cho server-side `search`: bỏ tiền tố hành chính (giữ dấu), mở rộng alias, giữ 'Quận 7' nguyên vẹn.
    'TP.HCM' -> 'Hồ Chí Minh'; 'Phường Linh Trung' -> 'Linh Trung'; 'q7' -> 'Quận 7'; 'Quận 7' -> 'Quận 7'."""
    raw = _dedot(name)
    key = admin_key(raw)
    if key in _ALIAS_DISPLAY:
        return _ALIAS_DISPLAY[key]
    nk = norm_key(raw)
    if m := _QN.match(nk):
        return f"Quận {m.group(1)}"
    if m := _PN.match(nk):
        return f"Phường {m.group(1)}"
    toks, ntoks = raw.split(), nk.split()
    for pfx, _lvl in _PREFIXES:
        ptoks = _dedot(pfx).split()
        if ntoks[: len(ptoks)] == ptoks and len(toks) > len(ptoks):
            rest = " ".join(toks[len(ptoks):])
            return raw if rest.isdigit() else rest
    return raw


def exact_matches(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    key = admin_key(name)
    return [r for r in rows if key and admin_key(r.get("name")) == key]


_exact = exact_matches   # tương thích tên cũ


@dataclass
class LocationResolution:
    kind: Kind
    city_id: Optional[int] = None
    district_id: Optional[int] = None
    ward_id: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    level: Optional[str] = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ids(self) -> dict[str, Optional[int]]:
        return {"city_id": self.city_id, "district_id": self.district_id, "ward_id": self.ward_id}


def _row_to_resolution(level: str, row: dict[str, Any], parent_city: Optional[int] = None, parent_district: Optional[int] = None) -> LocationResolution:
    if level == "city":
        return LocationResolution("admin", city_id=row.get("id"), level="city")
    if level == "district":
        return LocationResolution("admin", city_id=row.get("city_id") or parent_city, district_id=row.get("id"), level="district")
    return LocationResolution("admin", city_id=row.get("city_id") or parent_city, district_id=row.get("district_id") or parent_district,
                              ward_id=row.get("id"), level="ward")


def _lookup_exact(level: str, name: str, admin_lookup: AdminLookup, **scope: Any) -> list[dict[str, Any]]:
    try:
        rows = admin_lookup(level, search_term(name), **{k: v for k, v in scope.items() if v is not None}) or []
    except Exception:
        return []
    return exact_matches(rows, name)


def _enrich_admin_candidates(
    level: str,
    rows: list[dict[str, Any]],
    admin_lookup: AdminLookup,
    region_city: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Gắn thêm tên Quận/Huyện (cho Phường trùng tên) hoặc Tỉnh/Thành (cho Quận trùng tên) để người dùng phân biệt."""
    if len(rows) <= 1:
        return rows
    parent_map: dict[Any, str] = {}
    try:
        if level == "ward":
            districts = admin_lookup("district", "", city_id=region_city) or []
            parent_map = {d.get("id"): str(d.get("name")) for d in districts if d.get("id") is not None and d.get("name")}
        elif level == "district":
            cities = admin_lookup("city", "") or []
            parent_map = {c.get("id"): str(c.get("name")) for c in cities if c.get("id") is not None and c.get("name")}
    except Exception:
        parent_map = {}

    if not parent_map:
        return rows

    parent_key = "district_id" if level == "ward" else ("city_id" if level == "district" else "")
    enriched: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        pid = item.get(parent_key) if parent_key else None
        pname = parent_map.get(pid)
        if pname and pname.lower() not in str(item.get("name", "")).lower():
            item["name"] = f"{item.get('name')}, {pname}"
        enriched.append(item)
    return enriched


def resolve_admin(text: str, admin_lookup: AdminLookup, region_hint: Optional[str] = None) -> LocationResolution:
    """Chỉ thử phân giải như đơn vị hành chính. Trả kind='admin' | 'ambiguous' | 'admin_not_found'."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if not parts:
        return LocationResolution("admin_not_found")

    region_city: Optional[int] = None
    if region_hint:
        c = _lookup_exact("city", region_hint, admin_lookup)
        region_city = c[0].get("id") if len(c) == 1 else None

    # --- "Phường, Quận" hoặc "Quận, Thành phố"
    if len(parts) >= 2:
        d = _lookup_exact("district", parts[1], admin_lookup, city_id=region_city)
        if len(d) == 1:
            w = _lookup_exact("ward", parts[0], admin_lookup, district_id=d[0].get("id"))
            if len(w) == 1:
                return _row_to_resolution("ward", w[0], d[0].get("city_id") or region_city, d[0].get("id"))
        c = _lookup_exact("city", parts[1], admin_lookup)
        if len(c) == 1:
            dd = _lookup_exact("district", parts[0], admin_lookup, city_id=c[0].get("id"))
            if len(dd) == 1:
                return _row_to_resolution("district", dd[0], c[0].get("id"))
        return LocationResolution("admin_not_found")

    # --- một thành phần
    name = parts[0]
    hint = level_hint(name)
    order = [hint] + [lv for lv in ("city", "district", "ward") if lv != hint] if hint else ["city", "district", "ward"]
    for level in order:
        scope = {"city_id": region_city} if level in ("district", "ward") else {}
        rows = _lookup_exact(level, name, admin_lookup, **scope)
        if len(rows) == 1:
            return _row_to_resolution(level, rows[0], region_city)
        if len(rows) > 1:
            return LocationResolution("ambiguous", level=level, candidates=_enrich_admin_candidates(level, rows, admin_lookup, region_city))
    return LocationResolution("admin_not_found")


def resolve_location(
    text: str,
    kind: Optional[str],
    admin_lookup: AdminLookup,
    geocode: Geocode,
    region_hint: Optional[str] = None,
) -> LocationResolution:
    """kind: 'admin' | 'place' | None (chưa rõ: thử hành chính trước, trượt thì coi là địa điểm cụ thể)."""
    text = (text or "").strip()
    if not text:
        return LocationResolution("unresolved_point")

    if _PLACE_HINTS.search(text):
        kind = "place"

    if kind in ("admin", None):
        res = resolve_admin(text, admin_lookup, region_hint)
        if res.kind in ("admin", "ambiguous"):
            return res
        if kind == "admin":
            return res                       # NLU chắc chắn là hành chính mà DB không có -> "chưa có dữ liệu"

    # 'ĐH Bách Khoa, Hà Nội' -> geocode('ĐH Bách Khoa, Hà Nội', hint='Hà Nội') nếu chưa có hint
    hint = region_hint
    if hint is None and "," in text:
        tail = text.rsplit(",", 1)[1].strip()
        if _lookup_exact("city", tail, admin_lookup):
            hint = tail
    try:
        geo = geocode(text, hint)
    except Exception:
        geo = None
    if geo and geo.get("ambiguous") and geo.get("candidates"):
        return LocationResolution("ambiguous", level="place", candidates=list(geo["candidates"]))
    if geo and geo.get("lat") is not None and geo.get("lng") is not None:
        return LocationResolution("point", lat=float(geo["lat"]), lng=float(geo["lng"]))
    return LocationResolution("unresolved_point")
