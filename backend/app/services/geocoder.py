import re
import unicodedata
from typing import Optional
import requests
from app.schemas.geocode import GeocodeResponse

# Bounding box Việt Nam: minLon, minLat, maxLon, maxLat
VN_BBOX = "102.1,8.1,109.6,23.4"

# Pattern nhận diện và bóc tách các tiền tố học viện / cơ sở / trường học phổ biến
# giúp OpenStreetMap / Nominatim không bị loãng từ khoá
PREFIX_PATTERN = re.compile(
    r"^(?:trường\s+đại\s+học|đại\s+học|trường\s+đh|đh|trường|học\s+viện|ký\s+túc\s+xá|ktx)\s+",
    re.IGNORECASE,
)

def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").strip().lower()
    text = text.replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def geocode_nominatim(query: str) -> Optional[GeocodeResponse]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 3,
        "countrycodes": "vn",
        "accept-language": "vi",
    }
    headers = {"User-Agent": "SmartHousingPlatform/1.0 (contact@housing.internal)"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            for item in data or []:
                return GeocodeResponse(
                    query=query,
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                    formatted_address=item.get("display_name", query),
                    provider="Nominatim OSM",
                )
    except Exception:
        pass
    return None


def geocode_photon(query: str) -> Optional[GeocodeResponse]:
    url = "https://photon.komoot.io/api/"
    params = {"q": query, "limit": 5, "bbox": VN_BBOX}
    headers = {"User-Agent": "SmartHousingPlatform/1.0 (contact@housing.internal)"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        if res.status_code == 200:
            for f in res.json().get("features", []):
                props = f.get("properties", {})
                if props.get("countrycode") != "VN":
                    continue
                lon, lat = f["geometry"]["coordinates"]
                parts = [props.get(k) for k in
                         ("name", "street", "district", "city", "state")]
                addr = ", ".join(dict.fromkeys(p for p in parts if p))
                return GeocodeResponse(
                    query=query,
                    lat=float(lat),
                    lon=float(lon),
                    formatted_address=f"{addr}, Việt Nam",
                    provider="Photon Komoot",
                )
    except Exception:
        pass
    return None


def resolve_location(user_input: str, hint: Optional[str] = None) -> Optional[GeocodeResponse]:
    query = (user_input or "").strip()
    if not query:
        return None

    with_hint: list[str] = []
    no_hint: list[str] = []

    # 1. Truy vấn gốc
    if hint and hint.lower() not in query.lower():
        with_hint.append(f"{query}, {hint.strip()}")
    no_hint.append(query)

    # 2. Truy vấn đã lược bỏ tiền tố (trường học, ktx, viện...)
    stripped = PREFIX_PATTERN.sub("", query).strip()
    if stripped and stripped.lower() != query.lower() and len(stripped) >= 2:
        if hint and hint.lower() not in stripped.lower():
            with_hint.append(f"{stripped}, {hint.strip()}")
        no_hint.append(stripped)

    # Ưu tiên tất cả ứng viên có kèm hint tỉnh/thành trước khi thử không có hint
    candidates: list[str] = with_hint + no_hint

    # Thử lần lượt với Nominatim (chính xác cao nhất tại VN)
    for c in candidates:
        res = geocode_nominatim(c)
        if res:
            res.query = user_input
            return res

    # Nếu Nominatim không ra hoặc bị rate-limit, fallback sang Photon
    for c in candidates:
        res = geocode_photon(c)
        if res:
            res.query = user_input
            return res

    return None

