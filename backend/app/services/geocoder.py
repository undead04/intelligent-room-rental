import re
import json
import unicodedata
import requests
from app.schemas.geocode import GeocodeResponse
from typing import Optional

# Bounding box Việt Nam: minLon, minLat, maxLon, maxLat
VN_BBOX = "102.1,8.1,109.6,23.4"

# Danh bạ toạ độ các trường đại học và địa danh trọng điểm tại TP.HCM & Làng Đại học
KNOWN_LANDMARKS = [
    {
        "keywords": ["uit", "đại học uit", "đh uit", "dh uit", "công nghệ thông tin", "cntt", "truong uit", "trường uit"],
        "lat": 10.8698118,
        "lon": 106.8033668,
        "address": "Trường Đại học Công nghệ Thông tin - ĐHQG TP.HCM, Khu phố 6, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["ktx khu a", "ký túc xá khu a", "ky tuc xa khu a", "ktx a"],
        "lat": 10.8783,
        "lon": 106.8062,
        "address": "Ký túc xá Khu A ĐHQG TP.HCM, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["ktx khu b", "ký túc xá khu b", "ky tuc xa khu b", "ktx b"],
        "lat": 10.8824,
        "lon": 106.7825,
        "address": "Ký túc xá Khu B ĐHQG TP.HCM, Đông Hòa, Dĩ An, Bình Dương",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["khtn", "khoa học tự nhiên", "dh khtn", "đh khtn", "đại học khoa học tự nhiên"],
        "lat": 10.8757,
        "lon": 106.7995,
        "address": "Trường Đại học Khoa học Tự nhiên (Cơ sở 2) - ĐHQG TP.HCM, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["bách khoa", "bach khoa", "dhbk", "đhbk", "đại học bách khoa", "bku"],
        "lat": 10.8806,
        "lon": 106.8054,
        "address": "Trường Đại học Bách Khoa (Cơ sở 2) - ĐHQG TP.HCM, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["làng đại học", "lang dai hoc", "đại học quốc gia", "dhqg", "đhqg"],
        "lat": 10.8700,
        "lon": 106.8030,
        "address": "Khu đô thị Đại học Quốc gia TP.HCM, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["nông lâm", "nong lam", "dh nong lam", "đh nông lâm", "đại học nông lâm"],
        "lat": 10.8704,
        "lon": 106.7918,
        "address": "Trường Đại học Nông Lâm TP.HCM, Linh Trung, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["spkt", "sư phạm kỹ thuật", "su pham ky thuat", "đh sư phạm kỹ thuật"],
        "lat": 10.8506,
        "lon": 106.7720,
        "address": "Trường Đại học Sư phạm Kỹ thuật TP.HCM, 1 Võ Văn Ngân, Linh Chiểu, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["kinh tế luật", "kinh te luat", "uel", "đh kinh tế luật", "đại học kinh tế luật"],
        "lat": 10.8735,
        "lon": 106.7758,
        "address": "Trường Đại học Kinh tế - Luật - ĐHQG TP.HCM, 669 Quốc lộ 1A, Linh Xuân, TP. Thủ Đức, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
    {
        "keywords": ["hutech", "đại học công nghệ tp.hcm", "dh cong nghe"],
        "lat": 10.8014,
        "lon": 106.7145,
        "address": "Trường Đại học Công nghệ TP.HCM (HUTECH), 475A Điện Biên Phủ, Phường 25, Bình Thạnh, TP. Hồ Chí Minh",
        "provider": "Homigo University POI",
    },
]


def resolve_known_landmarks(query: str) -> Optional[GeocodeResponse]:
    """Kiểm tra đối sánh các địa danh đại học/ký túc xá quen thuộc với độ chính xác cao."""
    q_norm = unicodedata.normalize("NFC", query).lower().strip()
    for lm in KNOWN_LANDMARKS:
        for kw in lm["keywords"]:
            pattern = rf"(^|\b|\s){re.escape(kw)}(\b|\s|$)"
            if re.search(pattern, q_norm):
                return GeocodeResponse(
                    query=query,
                    lat=lm["lat"],
                    lon=lm["lon"],
                    formatted_address=lm["address"],
                    provider=lm["provider"],
                )
    return None


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
    # 1. Kiểm tra bảng địa danh đặc thù (UIT, KTX Khu A/B, ĐHQG...)
    known = resolve_known_landmarks(user_input)
    if known:
        return known

    cleaned_query = clean_input(user_input, hint)
    if not cleaned_query:
        return None

    # Kiểm tra lại known landmarks trên chuỗi đã làm sạch
    known = resolve_known_landmarks(cleaned_query)
    if known:
        return known

    # 2. Dự phòng tra cứu Nominatim OSM hoặc Photon Komoot
    result = geocode_nominatim(cleaned_query) or geocode_photon(cleaned_query)
    return result