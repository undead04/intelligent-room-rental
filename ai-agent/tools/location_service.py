"""Phân giải địa danh bằng CODE (không gọi LLM): hành chính -> (city_id, district_id, ward_id); địa điểm cụ thể -> (lat, lng).y).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from core.config import RESOLVE_LOCATION_MAX_RETRIES
from utils.text import norm_key

logger = logging.getLogger(__name__)

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
    r"\b(?:đh|trường|đại\s*học|học\s*viện|ký\s*túc\s*xá|ktx|bệnh\s*viện|bv|chợ|bến\s*xe|bx|kcn|khu\s*công\s*nghiệp|kcx|khu\s*chế\s*xuất|kcnc|khu\s*công\s*nghệ\s*cao|ga\s*metro|ga\s+[^\s]+|sân\s*bay|ngã\s*tư|ngã\s*sáu|ngã\s*6|vòng\s*xoay|tttm|trung\s*tâm\s*thương\s*mại|siêu\s*thị|mall|chung\s*cư|tòa\s*nhà|toà\s*nhà|công\s*viên)\b",
    re.IGNORECASE,
)


_ALIAS_DISPLAY = {   # alias -> tên chính thức CÓ DẤU, dùng làm từ khoá gửi lên server
    "ho chi minh": "Hồ Chí Minh", "ha noi": "Hà Nội", "da nang": "Đà Nẵng", "binh duong": "Bình Dương",
    "can tho": "Cần Thơ", "hai phong": "Hải Phòng", "dong nai": "Đồng Nai",
    "thu duc": "Thủ Đức",
}

CITY_ID_TO_REGION: dict[int, str] = {
    13: "Hồ Chí Minh",
    79: "Hồ Chí Minh",
    1: "Hà Nội",
    48: "Đà Nẵng",
    74: "Bình Dương",
    75: "Đồng Nai",
    92: "Cần Thơ",
}

REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Hồ Chí Minh": (
        "thu duc", "binh thanh", "go vap", "tan binh", "phu nhuan", "tan phu", "binh tan",
        "ho chi minh", "tp hcm", "tphcm", "sai gon", "saigon", "uit", "nha be", "hoc mon", "cu chi", "binh chanh", "can gio",
        "quan 1", "quan 2", "quan 3", "quan 4", "quan 5", "quan 6", "quan 7", "quan 8", "quan 9", "quan 10", "quan 11", "quan 12",
        "thao dien", "thu thiem", "phu my hung",
    ),
    "Hà Nội": (
        "ha noi", "hanoi", "cau giay", "hai ba trung", "dong da", "ba dinh", "hoan kiem",
        "thanh xuan", "ha dong", "tay ho", "nam tu liem", "bac tu liem", "long bien", "hoang mai",
        "gia lam", "dong anh", "hoa lac", "my dinh", "ho guom",
    ),
    "Bình Dương": ("binh duong", "di an", "thuan an", "thu dau mot", "ben cat", "tan uyen", "vsip", "my phuoc"),
    "Đà Nẵng": ("da nang", "danang", "hai chau", "lien chieu", "son tra", "ngu hanh son", "cam le", "thanh khe", "hoa khanh", "my khe"),
    "Đồng Nai": ("dong nai", "bien hoa", "long thanh", "nhon trach", "trang bom", "long khanh", "amata", "ngã tu vung tau", "nga tu vung tau"),
    "Cần Thơ": ("can tho", "ninh kieu", "binh thuy", "cai rang", "o mon", "thot not", "tra noc"),
}


def infer_region_from_location_text(location_text: Optional[str]) -> Optional[str]:
    """Nhận diện tên tỉnh/thành tương ứng từ tên địa danh hoặc quận/huyện tự do."""
    if not location_text:
        return None
    loc_k = norm_key(location_text)
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in loc_k for kw in keywords):
            return region
    return None


def infer_region_from_preference(pref: Any) -> Optional[str]:
    """Suy ra tỉnh/thành từ một trạng thái UserPreferenceState (theo city_id hoặc location_text)."""
    if pref is None:
        return None
    cid = getattr(pref, "city_id", None)
    if cid in CITY_ID_TO_REGION:
        return CITY_ID_TO_REGION[cid]
    return infer_region_from_location_text(getattr(pref, "location_text", None))


_PAREN_RE = re.compile(r"\s*\([^)]*\)")

_POI_CACHE: Optional[list[dict[str, Any]]] = None


def _load_local_pois() -> list[dict[str, Any]]:
    global _POI_CACHE
    if _POI_CACHE is not None:
        return _POI_CACHE
    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "university_campuses.json")
    try:
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                _POI_CACHE = json.load(f)
        else:
            _POI_CACHE = []
    except Exception:
        _POI_CACHE = []
    return _POI_CACHE


def _load_university_pois() -> list[dict[str, Any]]:
    """Tương thích ngược cho _load_local_pois()."""
    return _load_local_pois()


def _haversine_km_local(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _local_poi_enabled() -> bool:
    """Cho phép tắt/bật từ điển POI cục bộ qua HOMIGO_USE_LOCAL_POI (hạn chế phụ thuộc hardcode khi đã có Goong Places)."""
    return os.getenv("HOMIGO_USE_LOCAL_POI", "true").strip().lower() not in ("0", "false", "no", "off")


def lookup_local_poi_candidates(text: str, region_hint: Optional[str] = None) -> list[dict[str, Any]]:
    """Tra cứu các POI cục bộ khớp tên/alias (0 ms), có lọc theo region_hint nếu cung cấp."""
    if not text or not _local_poi_enabled():
        return []
    pois = _load_local_pois()
    if not pois:
        return []

    clean = re.sub(
        r"^(?:gần|quanh|khu\s+vực|ở|cạnh|đối\s+diện|tìm\s+phòng\s+(?:gần|quanh))\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    effective_hint = region_hint
    base_clean = clean
    if "," in clean:
        head_part, tail_part = [p.strip() for p in clean.rsplit(",", 1)]
        inferred_tail = infer_region_from_location_text(tail_part)
        if inferred_tail and head_part:
            base_clean = head_part
            effective_hint = effective_hint or inferred_tail

    clean_k = norm_key(clean)
    base_k = norm_key(base_clean)
    clean_k_sub = re.sub(r"^(?:truong|dh|dai hoc|hoc vien|ky tuc xa|ktx)\s+", "", base_k).strip()
    norm_hint = norm_key(effective_hint) if effective_hint else ""

    candidates: list[dict[str, Any]] = []
    for poi in pois:
        names = [poi.get("name", ""), poi.get("short_name", "")] + list(poi.get("aliases", []))
        norm_names = {norm_key(n) for n in names if n}
        if clean_k in norm_names or base_k in norm_names or (clean_k_sub and clean_k_sub in norm_names):
            candidates.append(poi)

    if not candidates:
        return []

    if len(candidates) > 1 and norm_hint:
        hinted = []
        for c in candidates:
            c_reg = norm_key(c.get("region", ""))
            if c_reg and (c_reg in norm_hint or norm_hint in c_reg):
                hinted.append(c)
        if hinted:
            return hinted

    return candidates


def lookup_university_poi(text: str, region_hint: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Tra cứu nhanh POI cục bộ từ từ điển (0 ms), trả 1 POI phù hợp nhất (giữ tương thích ngược)."""
    candidates = lookup_local_poi_candidates(text, region_hint)
    return candidates[0] if candidates else None


def find_poi_in_text(user_text: str, region_hint: Optional[str] = None) -> Optional[str]:
    """Dò tìm tên riêng/alias của POI cục bộ nằm nguyên cụm bên trong câu nói người dùng."""
    norm_u = norm_key(user_text or "")
    if not norm_u:
        return None
    pois = _load_local_pois()
    if not pois:
        return None

    hits: list[tuple[int, dict[str, Any]]] = []
    for poi in pois:
        names = [poi.get("name", ""), poi.get("short_name", "")] + list(poi.get("aliases", []))
        best_len = 0
        for raw_name in names:
            k = norm_key(raw_name)
            # Chỉ dò cụm từ >= 3 ký tự khớp nguyên ranh giới từ để tránh trùng ngẫu nhiên
            if len(k) < 3:
                continue
            if re.search(rf"(?:^|\s){re.escape(k)}(?:\s|$)", norm_u):
                best_len = max(best_len, len(k))
        if best_len > 0:
            hits.append((best_len, poi))

    if not hits:
        return None

    hits.sort(key=lambda item: item[0], reverse=True)
    max_len = hits[0][0]
    top_pois = [p for ln, p in hits if ln == max_len]
    if len(top_pois) > 1 and region_hint:
        norm_hint = norm_key(region_hint)
        for p in top_pois:
            p_reg = norm_key(p.get("region", ""))
            if p_reg and (p_reg in norm_hint or norm_hint in p_reg):
                return str(p.get("name") or "") or None
    return str(top_pois[0].get("name") or "") or None


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
            city_id = c[0].get("id")
            dd = _lookup_exact("district", parts[0], admin_lookup, city_id=city_id)
            if len(dd) == 1:
                return _row_to_resolution("district", dd[0], city_id)
            if len(dd) > 1:
                return LocationResolution("ambiguous", level="district", candidates=_enrich_admin_candidates("district", dd, admin_lookup, city_id))
            ww = _lookup_exact("ward", parts[0], admin_lookup, city_id=city_id)
            if len(ww) == 1:
                return _row_to_resolution("ward", ww[0], city_id, ww[0].get("district_id"))
            if len(ww) > 1:
                return LocationResolution("ambiguous", level="ward", candidates=_enrich_admin_candidates("ward", ww, admin_lookup, city_id))
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

    # Tra cứu nhanh POI cục bộ (0 ms, 0 LLM) trước khi kiểm tra admin_not_found / gọi Backend geocode
    poi_matches = lookup_local_poi_candidates(text, region_hint)
    valid_pois = [p for p in poi_matches if p.get("lat") is not None and p.get("lng") is not None]
    if valid_pois:
        clusters: list[dict[str, Any]] = []
        for p in valid_pois:
            p_lat, p_lng = float(p["lat"]), float(p["lng"])
            if not any(_haversine_km_local(p_lat, p_lng, float(c["lat"]), float(c["lng"])) <= 0.5 for c in clusters):
                clusters.append(p)
        if len(clusters) == 1:
            return LocationResolution("point", lat=float(clusters[0]["lat"]), lng=float(clusters[0]["lng"]))
        return LocationResolution(
            "ambiguous",
            level="place",
            candidates=[
                {
                    "name": str(c.get("name") or ""),
                    "lat": float(c["lat"]),
                    "lng": float(c["lng"]),
                    "address": str(c.get("address") or ""),
                    "region": str(c.get("region") or ""),
                }
                for c in clusters[:5]
            ],
        )

    if kind == "admin":
        return LocationResolution("admin_not_found")   # NLU chắc chắn là hành chính mà DB không có -> "chưa có dữ liệu"

    # 'ĐH Bách Khoa, Hà Nội' -> geocode('ĐH Bách Khoa, Hà Nội', hint='Hà Nội') nếu chưa có hint
    hint = region_hint
    if hint is None and "," in text:
        tail = text.rsplit(",", 1)[1].strip()
        if _lookup_exact("city", tail, admin_lookup) or _lookup_exact("district", tail, admin_lookup):
            hint = tail
        else:
            inferred = infer_region_from_location_text(tail)
            if inferred:
                hint = inferred
    try:
        geo = geocode(text, hint)
    except Exception:
        geo = None
    if geo and geo.get("ambiguous") and geo.get("candidates"):
        return LocationResolution("ambiguous", level="place", candidates=list(geo["candidates"]))
    if geo and geo.get("lat") is not None and geo.get("lng") is not None:
        return LocationResolution("point", lat=float(geo["lat"]), lng=float(geo["lng"]))
    return LocationResolution("unresolved_point")


class LocationRewrite(BaseModel):
    """Schema structured output cho bước viết lại địa danh khi resolve_location lần đầu thất bại."""

    rewritten_query: Optional[str] = Field(
        None,
        description="Tên địa danh chính thức ngắn gọn hơn (bỏ từ phụ như 'cổng sau', 'khu vực', sửa lỗi chính tả nếu có); null nếu không thể rút gọn",
    )
    location_kind: Optional[Literal["admin", "place"]] = Field(
        None,
        description="'admin' nếu là đơn vị hành chính (Tỉnh/Quận/Phường), 'place' nếu là địa điểm cụ thể/trường học/KCN",
    )


def _location_retry_variants(
    text: str,
    kind: Optional[str],
    failed_kind: Kind,
    region_hint: Optional[str],
) -> list[tuple[str, Optional[str], Optional[str]]]:
    """Sinh các biến thể cấu trúc nhẹ (không tốn LLM) khi lần phân giải đầu trả not_found."""
    variants: list[tuple[str, Optional[str], Optional[str]]] = []
    parts = [p.strip() for p in text.split(",") if p.strip()]

    if failed_kind == "admin_not_found":
        # Địa chỉ hành chính >= 3 phần ("Phường X, TP Thủ Đức, TP HCM") -> rút về (phần đầu, phần cuối) hoặc phần đầu + hint
        if len(parts) >= 3:
            variants.append((f"{parts[0]}, {parts[-1]}", kind, region_hint))
        if len(parts) >= 2:
            variants.append((parts[0], kind, region_hint or parts[-1]))
        return variants

    # Trường hợp unresolved_point: tách lõi trước dấu phẩy + dùng tail làm region_hint; hoặc rút ngắn prefix thừa
    if len(parts) >= 2:
        tail_hint = region_hint or infer_region_from_location_text(parts[-1]) or parts[-1]
        variants.append((parts[0], kind, tail_hint))

    # Gọt tiền tố mô tả vị trí thường gặp khi geocode thất bại ("cổng sau ...", "đối diện ...", "khu vực ...")
    stripped = re.sub(
        r"^(?:(?:cổng|cong)\s+(?:trước|truoc|sau|chính|chinh|phụ|phu)|khu\s+(?:vực|vuc)|gần|gan|quanh|đối\s+diện|doi\s+dien|bên\s+cạnh|ben\s+canh|cạnh|canh|sát|sat)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip(" ,.-")
    if stripped and norm_key(stripped) != norm_key(text):
        variants.append((stripped, kind, region_hint))
    return variants


def _rewrite_location_with_llm(
    text: str,
    region_hint: Optional[str],
    failed_kind: Kind,
    llm: Any,
) -> Optional[LocationRewrite]:
    """Nhờ Cloud LLM rút gọn / chuẩn hóa lại tên địa danh chính thức để thử phân giải lại."""
    if llm is None:
        return None
    prompt = (
        f"Địa danh '{text}' (khu vực gợi ý: '{region_hint or 'không rõ'}', trạng thái lỗi: {failed_kind}) "
        "vừa tra cứu bản đồ/hành chính không ra kết quả. "
        "Hãy viết lại 1 tên địa danh chính thức, ngắn gọn và chuẩn xác nhất ở Việt Nam để tìm kiếm lại (sửa lỗi chính tả, bỏ từ thừa như 'cổng sau', 'khu vực gần', tách rõ tên riêng). "
        "Nếu địa danh thực chất không xác định được hoặc là tỉnh ngoài vùng hỗ trợ thì giữ nguyên hoặc trả null."
    )
    try:
        raw = llm.with_structured_output(LocationRewrite).invoke([("human", prompt)])
        if raw is None:
            return None
        return raw if isinstance(raw, LocationRewrite) else LocationRewrite.model_validate(raw)
    except Exception:
        logger.warning("resolve_location_with_retry: LLM rewrite lỗi cho '%s'", text, exc_info=True)
        return None


def resolve_location_with_retry(
    text: str,
    kind: Optional[str],
    admin_lookup: AdminLookup,
    geocode: Geocode,
    region_hint: Optional[str] = None,
    *,
    max_retries: int = RESOLVE_LOCATION_MAX_RETRIES,
    llm: Any = None,
) -> tuple[LocationResolution, list[dict[str, Any]]]:
    """Phân giải địa danh có cơ chế retry tối đa `max_retries` lần khi gặp `admin_not_found` / `unresolved_point`.

    - Lần 0: gọi `resolve_location` với nguyên bản.
    - Retry 1: thử các biến thể cấu trúc chuỗi (tối đa 1 lần gọi thực tế khác query).
    - Retry 2 (nếu vẫn not_found và có `llm`): gọi Cloud LLM viết lại tên địa danh chuẩn xác hơn rồi thử lại.
    """
    attempts: list[dict[str, Any]] = []
    tried_keys: set[tuple[str, Optional[str], Optional[str]]] = set()

    def _run_once(q: str, k: Optional[str], h: Optional[str], stage: str) -> LocationResolution:
        tried_keys.add((norm_key(q), k, norm_key(h or "")))
        res = resolve_location(q, k, admin_lookup, geocode, h)
        attempts.append({
            "stage": stage,
            "query": q,
            "kind": k,
            "region_hint": h,
            "result_kind": res.kind,
        })
        return res

    res = _run_once(text, kind, region_hint, "primary")
    if res.kind in ("admin", "point", "ambiguous") or max_retries <= 0:
        return res, attempts

    retries_used = 0

    # Retry 1: biến thể cấu trúc chuỗi (không tốn LLM)
    for var_q, var_k, var_h in _location_retry_variants(text, kind, res.kind, region_hint):
        if retries_used >= max_retries:
            break
        key = (norm_key(var_q), var_k, norm_key(var_h or ""))
        if not var_q or key in tried_keys:
            continue
        retries_used += 1
        res = _run_once(var_q, var_k, var_h, f"retry_{retries_used}_variant")
        if res.kind in ("admin", "point", "ambiguous"):
            return res, attempts

    # Retry 2: Cloud LLM chuẩn hóa/rút gọn tên địa danh
    if retries_used < max_retries and llm is not None and (text or "").strip():
        rw = _rewrite_location_with_llm(text, region_hint, res.kind, llm)
        if rw and rw.rewritten_query:
            rw_q = rw.rewritten_query.strip()
            rw_k = rw.location_kind or kind
            key = (norm_key(rw_q), rw_k, norm_key(region_hint or ""))
            if rw_q and key not in tried_keys and norm_key(rw_q) != norm_key(text):
                retries_used += 1
                res = _run_once(rw_q, rw_k, region_hint, f"retry_{retries_used}_llm_rewrite")

    return res, attempts
