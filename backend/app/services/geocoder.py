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

ADMIN_OSM_TYPES = {
    "administrative", "state", "province", "city", "county", "district",
    "suburb", "quarter", "municipality", "country", "region", "town", "village",
}


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").strip().lower()
    text = text.replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_administrative_query(query: str) -> bool:
    """Trả về True nếu truy vấn chỉ là tên Tỉnh/Thành phố, Quận/Huyện, Phường/Xã (không phải địa điểm cụ thể)."""
    if not query or not query.strip():
        return False
    unaccented = _strip_accents(query)
    unaccented = re.sub(
        r"^((tim|o|gan|quanh|khu vuc|tai|xung quanh|phong|tro|bat ky dau|dau cung duoc)\s+)+",
        "",
        unaccented,
    ).strip()
    unaccented = re.sub(r"\s+(bat ky dau|dau cung duoc|gia re|phong tro|tro).*$", "", unaccented).strip()
    if not unaccented:
        return False

    padded = f" {unaccented} "
    for kw in SPECIFIC_POI_KEYWORDS_UNACCENTED:
        if f" {kw.strip()} " in padded or unaccented.startswith(kw):
            return False

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
            if remainder and not any(f" {kw.strip()} " in rem_padded or remainder.startswith(kw) for kw in SPECIFIC_POI_KEYWORDS_UNACCENTED):
                continue
        return False
    return True


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
                osm_class = (item.get("class") or "").lower()
                osm_type = (item.get("type") or "").lower()
                addr_type = (item.get("addresstype") or "").lower()
                # Không trả về toạ độ tâm của ranh giới hành chính (Tỉnh/Thành, Quận/Huyện, Phường/Xã)
                if osm_class == "boundary" or osm_type in ADMIN_OSM_TYPES or addr_type in ADMIN_OSM_TYPES:
                    continue
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
                osm_key = (props.get("osm_key") or "").lower()
                osm_val = (props.get("osm_value") or "").lower()
                obj_type = (props.get("type") or "").lower()
                if osm_key == "boundary" or osm_val in ADMIN_OSM_TYPES or obj_type in ("state", "city", "district", "county", "locality"):
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

    # 2. Nếu đầu vào của người dùng chỉ là đơn vị hành chính (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã) -> không trả về lat, lon
    if is_administrative_query(user_input):
        return None

    cleaned_query = clean_input(user_input, hint)
    if not cleaned_query:
        return None

    # Kiểm tra lại known landmarks trên chuỗi đã làm sạch
    known = resolve_known_landmarks(cleaned_query)
    if known:
        return known

    # 3. Dự phòng tra cứu Nominatim OSM hoặc Photon Komoot (chỉ cho địa điểm cụ thể / đường phố)
    result = geocode_nominatim(cleaned_query) or geocode_photon(cleaned_query)
    return result