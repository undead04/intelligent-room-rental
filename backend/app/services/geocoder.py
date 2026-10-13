import re
import json
import unicodedata
import requests
from app.schemas.geocode import GeocodeResponse
from typing import Optional

# Bounding box Việt Nam: minLon, minLat, maxLon, maxLat
VN_BBOX = "102.1,8.1,109.6,23.4"


def clean_input(raw_input: str, hint: Optional[str] = None) -> str:
    """Làm sạch câu chat. Không ép địa danh nào; chỉ thêm hint nếu có."""
    text = unicodedata.normalize("NFC", raw_input).strip()

    patterns = [
        r"^((tìm|ở|gần|quanh|khu vực|tại|xung quanh|phòng|trọ)\s+)+",
        r"\s+(giá rẻ|phòng trọ|trọ|căn hộ|chung cư).*$",
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)

    if hint:
        hint = unicodedata.normalize("NFC", hint).strip()
        if hint.lower() not in text.lower():
            text += f", {hint}"
    return text


def geocode_nominatim(query: str) -> Optional[GeocodeResponse]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "vn",
        "accept-language": "vi",
    }
    headers = {"User-Agent": "SmartHousingPlatform/1.0 (contact@housing.internal)"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data:
                item = data[0]
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
    try:
        res = requests.get(url, params=params, timeout=3)
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
    """hint: tỉnh/thành để thu hẹp khi tên bị trùng (vd: 'Đà Nẵng')."""
    cleaned_query = clean_input(user_input, hint)
    if not cleaned_query:
        return None

    result = geocode_nominatim(cleaned_query) or geocode_photon(cleaned_query)
    return result