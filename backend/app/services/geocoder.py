import json
import math
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Optional

import requests

from app.core.config import settings
from app.core.paths import GEOCODE_CACHE_DB_PATH
from app.schemas.geocode import GeocodeCandidate, GeocodeResponse

# Bounding box Việt Nam: minLon, minLat, maxLon, maxLat
VN_BBOX = "102.1,8.1,109.6,23.4"

# Bounding box tọa độ cho 6 vùng/tỉnh thành hỗ trợ: (min_lon, min_lat, max_lon, max_lat)
# Lưu ý: TP.HCM và Bình Dương cho phép giao thoa hợp lý quanh Làng ĐH Thủ Đức - Dĩ An (10.87, 106.80).
REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "TP.HCM": (106.34, 10.35, 107.05, 11.16),
    "Hà Nội": (105.28, 20.55, 106.03, 21.39),
    "Đà Nẵng": (107.80, 15.90, 108.40, 16.26),
    "Bình Dương": (106.33, 10.84, 107.02, 11.50),
    "Đồng Nai": (106.75, 10.55, 107.58, 11.58),
    "Cần Thơ": (105.20, 9.90, 105.86, 10.35),
}

_REGION_HINT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "TP.HCM": (
        "tp ho chi minh", "ho chi minh", "thanh pho ho chi minh", "tp hcm", "tphcm",
        "sai gon", "saigon", "hcm", "thu duc", "binh thanh", "go vap", "tan binh",
        "phu nhuan", "tan phu", "binh tan", "nha be", "hoc mon", "cu chi", "binh chanh", "can gio",
        "quan 1", "quan 2", "quan 3", "quan 4", "quan 5", "quan 6",
        "quan 7", "quan 8", "quan 9", "quan 10", "quan 11", "quan 12",
    ),
    "Hà Nội": (
        "ha noi", "hanoi", "cau giay", "hai ba trung", "dong da", "ba dinh", "hoan kiem",
        "thanh xuan", "ha dong", "tay ho", "nam tu liem", "bac tu liem", "long bien",
        "hoang mai", "gia lam", "dong anh", "hoai duc", "thanh tri", "soc son", "son tay", "thach that",
    ),
    "Đà Nẵng": (
        "da nang", "danang", "hai chau", "lien chieu", "son tra",
        "ngu hanh son", "cam le", "thanh khe", "hoa vang",
    ),
    "Bình Dương": (
        "binh duong", "di an", "thuan an", "thu dau mot",
        "ben cat", "tan uyen", "bau bang", "phu giao", "dau tieng",
    ),
    "Đồng Nai": (
        "dong nai", "bien hoa", "long thanh", "nhon trach",
        "trang bom", "long khanh", "vinh cuu", "xuan loc", "dinh quan", "cam my",
    ),
    "Cần Thơ": (
        "can tho", "ninh kieu", "binh thuy", "cai rang",
        "o mon", "thot not", "phong dien", "co do", "vinh thanh", "thoi lai",
    ),
}

AMBIGUOUS_CLUSTER_KM = 0.5
_DEFAULT_HEADERS = {"User-Agent": "SmartHousingPlatform/1.0 (contact@housing.internal)"}

# Pattern nhận diện và bóc tách các tiền tố học viện / cơ sở / trường học phổ biến
# giúp OpenStreetMap / Nominatim không bị loãng từ khoá
PREFIX_PATTERN = re.compile(
    r"^(?:trường\s+đại\s+học|đại\s+học|trường\s+đh|đh|trường|học\s+viện|ký\s*túc\s*xá|ktx)\s+",
    re.IGNORECASE,
)

# Tái sử dụng HTTP connection pool qua Session cho geocoding requests
_session = requests.Session()


def _norm_text(s: Optional[str]) -> str:
    """Chuẩn hoá văn bản tiếng Việt: bỏ dấu, chuyển đ->d, lowercase, gộp khoảng trắng."""
    raw = (s or "").strip()
    if not raw:
        return ""
    text = unicodedata.normalize("NFD", raw)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "d").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def infer_target_region(hint: Optional[str]) -> Optional[str]:
    """Suy ra vùng chuẩn (trong 6 vùng hỗ trợ) từ chuỗi hint tỉnh/thành hoặc quận/huyện."""
    norm = _norm_text(hint)
    if not norm:
        return None
    # Duyệt từ khóa dài trước để tránh 'quan 1' khớp nhầm 'quan 10'
    matches: list[tuple[int, str]] = []
    for region, keywords in _REGION_HINT_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"(?:^|\s){re.escape(kw)}(?:\s|$)", norm):
                matches.append((len(kw), region))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def is_in_vietnam(lat: float, lon: float) -> bool:
    """Kiểm tra tọa độ có nằm trong bounding box Việt Nam không."""
    return 8.1 <= lat <= 23.4 and 102.1 <= lon <= 109.6


def is_in_region_bbox(lat: float, lon: float, target_region: Optional[str]) -> bool:
    """Kiểm tra tọa độ nằm trong Việt Nam và khớp vùng (nếu target_region xác định được)."""
    if not is_in_vietnam(lat, lon):
        return False
    if target_region and target_region in REGION_BBOXES:
        min_lon, min_lat, max_lon, max_lat = REGION_BBOXES[target_region]
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
    return True


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách Haversine (km) giữa 2 tọa độ WGS84."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _build_short_name(primary: Optional[str], display: str) -> str:
    """Rút gọn tên hiển thị phục vụ chip chọn địa điểm khi có kết quả ambiguous."""
    parts = [p.strip() for p in (display or "").split(",") if p.strip()]
    filtered = [
        p for p in parts
        if _norm_text(p) not in ("viet nam", "vietnam") and not re.fullmatch(r"\d{5,6}", p)
    ]
    if primary and primary.strip():
        head = primary.strip()
        rest = [p for p in filtered if _norm_text(p) != _norm_text(head)]
        picked = [head] + rest[:2]
    else:
        picked = filtered[:3] if filtered else parts[:2]
    label = ", ".join(picked).strip()
    if len(label) > 90:
        label = label[:87].rstrip(" ,") + "..."
    return label or display[:90]


def _cluster_candidates(
    candidates: list[GeocodeCandidate],
    threshold_km: float = AMBIGUOUS_CLUSTER_KM,
) -> list[GeocodeCandidate]:
    """Gom cụm ứng viên gần nhau <= threshold_km (mặc định 500m) theo thứ tự ưu tiên."""
    clusters: list[GeocodeCandidate] = []
    for cand in candidates:
        too_close = any(
            _haversine_km(cand.lat, cand.lon, rep.lat, rep.lon) <= threshold_km
            for rep in clusters
        )
        if not too_close:
            clusters.append(cand.model_copy())
        if len(clusters) >= 5:
            break

    # Tránh trùng tên nút chọn nếu nhiều cụm phân tán ngẫu nhiên có tên rút gọn giống nhau
    seen_names: dict[str, int] = {}
    for idx, cand in enumerate(clusters):
        key = _norm_text(cand.name)
        if key in seen_names:
            # Bổ sung thêm phần địa chỉ đầy đủ để phân biệt
            parts = [p.strip() for p in cand.formatted_address.split(",") if p.strip()]
            suffix = ", ".join(parts[1:4]) if len(parts) > 1 else f"#{idx + 1}"
            cand.name = f"{cand.name} ({suffix})"[:95]
        seen_names[_norm_text(cand.name)] = idx
    return clusters


class GeocodeCache:
    """Persistent SQLite geocode cache kèm TTL theo cặp (query_norm, hint_norm)."""

    def __init__(self, db_path: Path = GEOCODE_CACHE_DB_PATH, ttl_seconds: Optional[int] = None) -> None:
        self.db_path = Path(db_path)
        self.ttl_seconds = (
            settings.GEOCODE_CACHE_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
        )
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS geocode_cache (
                            cache_key TEXT PRIMARY KEY,
                            query_norm TEXT NOT NULL,
                            hint_norm TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            expires_at REAL NOT NULL
                        )
                        """
                    )
            finally:
                conn.close()

    @staticmethod
    def make_key(query: str, hint: Optional[str]) -> tuple[str, str, str]:
        qn = _norm_text(query)
        hn = _norm_text(hint)
        return f"{qn}||{hn}", qn, hn

    def get(self, query: str, hint: Optional[str] = None, *, now: Optional[float] = None) -> Optional[GeocodeResponse]:
        if self.ttl_seconds <= 0:
            return None
        key, _, _ = self.make_key(query, hint)
        ts = time.time() if now is None else now
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT payload_json, expires_at FROM geocode_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
                if not row:
                    return None
                payload_json, expires_at = row
                if ts >= float(expires_at):
                    with conn:
                        conn.execute("DELETE FROM geocode_cache WHERE cache_key = ?", (key,))
                    return None
                return GeocodeResponse.model_validate(json.loads(payload_json))
            except Exception:
                return None
            finally:
                conn.close()

    def set(
        self,
        query: str,
        hint: Optional[str],
        response: GeocodeResponse,
        *,
        now: Optional[float] = None,
    ) -> None:
        if self.ttl_seconds <= 0:
            return
        key, qn, hn = self.make_key(query, hint)
        ts = time.time() if now is None else now
        expires_at = ts + self.ttl_seconds
        payload = response.model_dump(mode="json")
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO geocode_cache
                            (cache_key, query_norm, hint_norm, payload_json, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (key, qn, hn, json.dumps(payload, ensure_ascii=False), ts, expires_at),
                    )
            finally:
                conn.close()

    def clear(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("DELETE FROM geocode_cache")
            finally:
                conn.close()


_default_cache_lock = threading.Lock()
_default_cache: Optional[GeocodeCache] = None


def get_geocode_cache() -> GeocodeCache:
    """Lấy singleton GeocodeCache gắn với GEOCODE_CACHE_DB_PATH."""
    global _default_cache
    with _default_cache_lock:
        if _default_cache is None or _default_cache.db_path != Path(GEOCODE_CACHE_DB_PATH):
            _default_cache = GeocodeCache(db_path=Path(GEOCODE_CACHE_DB_PATH))
        return _default_cache


def clear_geocode_cache() -> None:
    """Xoá toàn bộ bản ghi trong persistent geocode cache (hữu ích cho test / reset)."""
    get_geocode_cache().clear()


def geocode_goong_candidates(
    query: str,
    api_key: Optional[str] = None,
    *,
    target_region: Optional[str] = None,
    limit: int = 5,
) -> list[GeocodeCandidate]:
    """Hook tùy chọn gọi Goong Geocode API khi cấu hình GOONG_API_KEY."""
    key = (api_key or settings.GOONG_API_KEY or "").strip()
    clean = (query or "").strip()
    if not key or not clean:
        return []
    url = "https://rsapi.goong.io/geocode"
    params = {"address": clean, "api_key": key}
    out: list[GeocodeCandidate] = []
    try:
        res = _session.get(url, params=params, headers=_DEFAULT_HEADERS, timeout=3)
        if res.status_code != 200:
            return []
        for item in (res.json().get("results") or [])[:limit]:
            loc = (item.get("geometry") or {}).get("location") or {}
            lat = loc.get("lat")
            lon = loc.get("lng", loc.get("lon"))
            if lat is None or lon is None:
                continue
            lat_f, lon_f = float(lat), float(lon)
            if not is_in_region_bbox(lat_f, lon_f, target_region):
                continue
            addr = str(item.get("formatted_address") or clean)
            out.append(
                GeocodeCandidate(
                    name=_build_short_name(item.get("name"), addr),
                    lat=lat_f,
                    lon=lon_f,
                    formatted_address=addr,
                    provider="Goong Maps",
                )
            )
    except Exception:
        return []
    return out


def geocode_nominatim_candidates(
    query: str,
    *,
    target_region: Optional[str] = None,
    limit: int = 5,
) -> list[GeocodeCandidate]:
    """Lấy tối đa top `limit` ứng viên Nominatim hợp lệ trong Việt Nam và vùng target_region."""
    clean = (query or "").strip()
    if not clean:
        return []
    url = "https://nominatim.openstreetmap.org/search"
    params: dict[str, object] = {
        "q": clean,
        "format": "json",
        "limit": limit,
        "countrycodes": "vn",
        "accept-language": "vi",
    }
    if target_region and target_region in REGION_BBOXES:
        min_lon, min_lat, max_lon, max_lat = REGION_BBOXES[target_region]
        # viewbox theo định dạng Nominatim: left,top,right,bottom (không ép bounded=1 để tương thích mock)
        params["viewbox"] = f"{min_lon},{max_lat},{max_lon},{min_lat}"

    out: list[GeocodeCandidate] = []
    try:
        res = _session.get(url, params=params, headers=_DEFAULT_HEADERS, timeout=3)
        if res.status_code != 200:
            return []
        for item in res.json() or []:
            lat_f = float(item["lat"])
            lon_f = float(item["lon"])
            if not is_in_region_bbox(lat_f, lon_f, target_region):
                continue
            display = str(item.get("display_name") or clean)
            out.append(
                GeocodeCandidate(
                    name=_build_short_name(item.get("name"), display),
                    lat=lat_f,
                    lon=lon_f,
                    formatted_address=display,
                    provider="Nominatim OSM",
                )
            )
    except Exception:
        return []
    return out


def geocode_photon_candidates(
    query: str,
    *,
    target_region: Optional[str] = None,
    limit: int = 5,
) -> list[GeocodeCandidate]:
    """Lấy tối đa top `limit` ứng viên Photon hợp lệ trong Việt Nam và vùng target_region."""
    clean = (query or "").strip()
    if not clean:
        return []
    url = "https://photon.komoot.io/api/"
    bbox = VN_BBOX
    if target_region and target_region in REGION_BBOXES:
        min_lon, min_lat, max_lon, max_lat = REGION_BBOXES[target_region]
        bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    params = {"q": clean, "limit": limit, "bbox": bbox}
    out: list[GeocodeCandidate] = []
    try:
        res = _session.get(url, params=params, headers=_DEFAULT_HEADERS, timeout=3)
        if res.status_code != 200:
            return []
        for f in res.json().get("features", []):
            props = f.get("properties", {})
            if props.get("countrycode") != "VN":
                continue
            lon_val, lat_val = f["geometry"]["coordinates"]
            lat_f, lon_f = float(lat_val), float(lon_val)
            if not is_in_region_bbox(lat_f, lon_f, target_region):
                continue
            parts = [props.get(k) for k in ("name", "street", "district", "city", "state")]
            addr = ", ".join(dict.fromkeys(p for p in parts if p))
            formatted = f"{addr}, Việt Nam" if addr else f"{clean}, Việt Nam"
            out.append(
                GeocodeCandidate(
                    name=_build_short_name(props.get("name"), addr or clean),
                    lat=lat_f,
                    lon=lon_f,
                    formatted_address=formatted,
                    provider="Photon Komoot",
                )
            )
    except Exception:
        return []
    return out


def _candidates_to_response(original_query: str, candidates: list[GeocodeCandidate]) -> Optional[GeocodeResponse]:
    """Chuyển danh sách ứng viên thành 1 điểm duy nhất hoặc response ambiguous (>500m)."""
    clusters = _cluster_candidates(candidates, threshold_km=AMBIGUOUS_CLUSTER_KM)
    if not clusters:
        return None
    if len(clusters) == 1:
        best = clusters[0]
        return GeocodeResponse(
            query=original_query,
            lat=best.lat,
            lon=best.lon,
            formatted_address=best.formatted_address,
            provider=best.provider,
            ambiguous=False,
            candidates=[],
        )
    return GeocodeResponse(
        query=original_query,
        lat=None,
        lon=None,
        formatted_address="",
        provider=clusters[0].provider,
        ambiguous=True,
        candidates=clusters,
    )


def geocode_nominatim(query: str) -> Optional[GeocodeResponse]:
    """Tra cứu một truy vấn qua Nominatim (tương thích ngược)."""
    cands = geocode_nominatim_candidates(query, limit=5)
    return _candidates_to_response(query, cands)


class _NominatimCacheShim:
    """Shim tương thích ngược cho caller/test gọi `_lookup_nominatim_cached.cache_clear()`."""

    def cache_clear(self) -> None:
        clear_geocode_cache()

    def __call__(self, query_lower: str) -> tuple[float, float, str, str]:
        cands = geocode_nominatim_candidates(query_lower, limit=3)
        if not cands:
            raise ValueError(f"Nominatim not found for: {query_lower}")
        first = cands[0]
        return (first.lat, first.lon, first.formatted_address, first.provider)


_lookup_nominatim_cached = _NominatimCacheShim()


def geocode_photon(query: str) -> Optional[GeocodeResponse]:
    """Tra cứu một truy vấn qua Photon (tương thích ngược)."""
    cands = geocode_photon_candidates(query, limit=5)
    return _candidates_to_response(query, cands)


def resolve_location(
    user_input: str,
    hint: Optional[str] = None,
    *,
    cache: Optional[GeocodeCache] = None,
    use_cache: bool = True,
) -> Optional[GeocodeResponse]:
    """Phân giải tên địa điểm thành toạ độ hoặc danh sách ứng viên ambiguous trong 6 vùng hỗ trợ."""
    query = (user_input or "").strip()
    if not query:
        return None

    target_region = infer_target_region(hint)
    active_cache = cache or (get_geocode_cache() if use_cache else None)
    if use_cache and active_cache is not None:
        cached = active_cache.get(query, hint)
        if cached is not None:
            cached.query = user_input
            return cached

    with_hint: list[str] = []
    no_hint: list[str] = []

    hint_clean = (hint or "").strip()
    norm_query = _norm_text(query)
    norm_hint = _norm_text(hint_clean)

    # 1. Truy vấn gốc
    if hint_clean and norm_hint and norm_hint not in norm_query:
        with_hint.append(f"{query}, {hint_clean}")
    no_hint.append(query)

    # 2. Truy vấn đã lược bỏ tiền tố (trường học, ktx, viện...)
    stripped = PREFIX_PATTERN.sub("", query).strip()
    norm_stripped = _norm_text(stripped)
    if stripped and norm_stripped != norm_query and len(stripped) >= 2:
        if hint_clean and norm_hint and norm_hint not in norm_stripped:
            with_hint.append(f"{stripped}, {hint_clean}")
        no_hint.append(stripped)

    # Ưu tiên tất cả biến thể kèm hint trước, nhưng vẫn giữ lọc region bbox ở mọi bước
    query_variants: list[str] = list(dict.fromkeys(with_hint + no_hint))

    providers = []
    if (settings.GOONG_API_KEY or "").strip():
        providers.append(lambda q_str: geocode_goong_candidates(q_str, target_region=target_region, limit=5))
    providers.append(lambda q_str: geocode_nominatim_candidates(q_str, target_region=target_region, limit=5))
    providers.append(lambda q_str: geocode_photon_candidates(q_str, target_region=target_region, limit=5))

    for fetch_candidates in providers:
        for variant in query_variants:
            cands = fetch_candidates(variant)
            if not cands:
                continue
            resp = _candidates_to_response(user_input, cands)
            if resp is not None:
                if use_cache and active_cache is not None:
                    active_cache.set(query, hint, resp)
                return resp

    return None
