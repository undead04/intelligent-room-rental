import unicodedata
from typing import Optional
import requests
from app.schemas.geocode import GeocodeResponse

# Bounding box Việt Nam: minLon, minLat, maxLon, maxLat
VN_BBOX = "102.1,8.1,109.6,23.4"

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
    query = user_input.strip()
    if hint and hint.lower() not in query.lower():
        query = f"{query}, {hint.strip()}"

    return geocode_nominatim(query) or geocode_photon(query)
