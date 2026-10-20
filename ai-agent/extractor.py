"""Module trích xuất nhu cầu, loại phòng (RoomType) và tiện ích (AmenityCode) bằng LLM.
Sử dụng trực tiếp taxonomy chuẩn hóa AmenityCode và RoomType của hệ thống Homigo.
LLM tự động suy luận và ánh xạ trực tiếp sang các mã canonical mà không cần từ điển map thủ công.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from schemas import UserPreferenceState

logger = logging.getLogger(__name__)

# Danh mục 17 mã tiện ích, an ninh và quy định chuẩn hóa (AmenityCode) của Homigo
CANONICAL_AMENITIES: set[str] = {
    # 1. Tiện ích phòng cốt lõi (Core Amenities)
    "private_wc",          # WC riêng, khép kín
    "aircon",              # Máy lạnh, điều hòa
    "mezzanine",           # Gác lửng, gác xép
    "kitchen",             # Kệ bếp, khu nấu ăn riêng
    "fridge",              # Tủ lạnh
    "washing_machine",     # Máy giặt (chung hoặc riêng)
    "window_balcony",      # Ban công hoặc cửa sổ thoáng
    "furniture",           # Đầy đủ nội thất (giường, tủ, bàn ghế...)
    "parking",             # Chỗ để xe trong nhà / hầm xe
    "elevator",            # Thang máy

    # 2. Quy định & Lối sống (Rules & Lifestyle)
    "free_hours",          # Giờ giấc tự do (không khóa cổng)
    "no_shared_landlord",  # Không chung chủ
    "pet_allowed",         # Cho phép nuôi thú cưng (chó, mèo)

    # 3. An toàn & An ninh (Safety)
    "fingerprint_lock",    # Khóa vân tay, cổng thẻ từ
    "camera",              # Camera an ninh 24/7
    "guard",               # Bảo vệ trực cổng 24/7
    "safe_area",           # Khu vực an ninh, yên tĩnh
}

# Tương thích ngược: map từ code sang tên hiển thị ngắn gọn khi cần
AMENITY_CATALOG: dict[str, str] = {
    "private_wc": "WC riêng, khép kín",
    "aircon": "Máy lạnh, điều hòa",
    "mezzanine": "Gác lửng, gác xép",
    "kitchen": "Kệ bếp, khu nấu ăn riêng",
    "fridge": "Tủ lạnh",
    "washing_machine": "Máy giặt",
    "window_balcony": "Ban công, cửa sổ thoáng",
    "furniture": "Đầy đủ nội thất",
    "parking": "Chỗ để xe, hầm xe",
    "elevator": "Thang máy",
    "free_hours": "Giờ giấc tự do 24/7",
    "no_shared_landlord": "Không chung chủ",
    "pet_allowed": "Cho nuôi thú cưng (chó, mèo)",
    "fingerprint_lock": "Khóa vân tay, thẻ từ",
    "camera": "Camera an ninh",
    "guard": "Bảo vệ trực cổng 24/7",
    "safe_area": "Khu vực an ninh, yên tĩnh",
}

# Danh mục phân loại phòng trọ chuẩn hóa (RoomType)
CANONICAL_ROOM_TYPES: set[str] = {
    "ROOM",         # Phòng trọ truyền thống
    "STUDIO",       # Căn hộ mini, studio
    "APARTMENT",    # Căn hộ chung cư, chung cư dịch vụ
    "SLEEPBOX",     # Ký túc xá, sleepbox, giường tầng
    "WHOLE_HOUSE",  # Nhà nguyên căn
}

ROOM_TYPE_CODE_TO_ID: dict[str, int] = {
    "ROOM": 1,
    "STUDIO": 2,
    "APARTMENT": 3,
    "SLEEPBOX": 4,
    "WHOLE_HOUSE": 5,
}

ROOM_TYPE_ID_TO_CODE: dict[int, str] = {
    1: "ROOM",
    2: "STUDIO",
    3: "APARTMENT",
    4: "SLEEPBOX",
    5: "WHOLE_HOUSE",
}


EXTRACTION_SYSTEM_PROMPT = """Bạn là trợ lý AI chuyên trích xuất tiêu chí tìm kiếm phòng trọ cho hệ thống Homigo.
Nhiệm vụ của bạn là đọc câu nói của người dùng và trích xuất các tiêu chí tìm phòng dưới dạng JSON duy nhất.

1. DANH MỤC TIỆN ÍCH CHUẨN (AMENITY CODES) - CHỈ TRẢ VỀ CÁC MÃ DƯỚI ĐÂY:
- `private_wc`: WC riêng, vệ sinh riêng, toilet riêng, toilet trong phòng, khép kín.
- `aircon`: Máy lạnh, điều hòa, ac.
- `mezzanine`: Gác lửng, gác xép, gác đúc, phòng có gác.
- `kitchen`: Kệ bếp, bếp riêng, khu nấu ăn, cho nấu ăn.
- `fridge`: Tủ lạnh.
- `washing_machine`: Máy giặt, chỗ giặt đồ.
- `window_balcony`: Ban công, cửa sổ, phòng thoáng mát, view thoáng.
- `furniture`: Đầy đủ nội thất, full nội thất, giường nệm tủ bàn ghế.
- `parking`: Chỗ để xe, giữ xe, nhà xe, hầm để xe.
- `elevator`: Thang máy.
- `free_hours`: Giờ giấc tự do, 24/24, không giới nghiêm.
- `no_shared_landlord`: Không chung chủ, lối đi riêng, tự do.
- `pet_allowed`: Cho nuôi thú cưng, nuôi chó, nuôi mèo, nuôi pet, boss.
- `fingerprint_lock`: Khóa vân tay, thẻ từ, khóa thông minh.
- `camera`: Camera an ninh 24/7.
- `guard`: Bảo vệ trực cổng 24/7.
- `safe_area`: Khu vực an ninh, yên tĩnh.

2. PHÂN LOẠI PHÒNG TRỌ (ROOM TYPE) - CHỈ CHỌN 1 TRONG 5 MÃ HOẶC NULL:
- `ROOM`: Phòng trọ truyền thống, phòng đơn, phòng trọ sinh viên.
- `STUDIO`: Căn hộ mini, studio, phòng studio full đồ.
- `APARTMENT`: Căn hộ chung cư, chung cư dịch vụ.
- `SLEEPBOX`: Ký túc xá, sleepbox, giường tầng, box ngủ.
- `WHOLE_HOUSE`: Nhà nguyên căn.

QUY TẮC TRÍCH XUẤT:
1. `location_text`: Tên địa điểm, khu vực, quận huyện, phường xã hoặc trường học/công ty người dùng muốn tìm. Nếu không nhắc thì để null.
2. `room_type`: Mã loại phòng chuẩn (ROOM, STUDIO, APARTMENT, SLEEPBOX, WHOLE_HOUSE) hoặc null nếu không rõ.
3. `min_price`: Mức giá tối thiểu bằng số VNĐ (ví dụ: 'từ 2 triệu' -> 2000000). Nếu không có để null.
4. `max_price`: Mức giá tối đa bằng số VNĐ (ví dụ: 'dưới 3.5tr' -> 3500000, 'tầm 4 triệu' -> 4000000). Nếu không có để null.
5. `min_area`: Diện tích tối thiểu bằng số m2. Nếu không có để null.
6. `max_area`: Diện tích tối đa bằng số m2. Nếu không có để null.
7. `amenities`: Mảng danh sách các mã canonical AmenityCode ở trên (ví dụ: ["aircon", "mezzanine"]). Tuyệt đối KHÔNG trả về từ ngữ tiếng Việt trong mảng này.
8. `special_requirements`: Mảng các yêu cầu mềm khác như 'yên tĩnh', 'sạch sẽ', 'đường không ngập'.

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC (Chỉ trả về JSON thuần, không bọc giải thích):
{
  "location_text": null,
  "room_type": null,
  "min_price": null,
  "max_price": null,
  "min_area": null,
  "max_area": null,
  "amenities": [],
  "special_requirements": []
}"""


class ExtractedPreference(BaseModel):
    location_text: Optional[str] = None
    room_type: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    amenities: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)


def _clean_json_response(raw_text: str) -> str:
    """Loại bỏ markdown codeblock ```json ... ``` nếu LLM bao bọc."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _fallback_extract(text: str) -> ExtractedPreference:
    """Bộ trích xuất dự phòng nhẹ khi LLM không khả dụng (offline / test)."""
    clean = text.lower()
    res = ExtractedPreference()

    # 1. Loại phòng (Room Type - kiểm tra từ cụ thể đến khái quát)
    if "nguyên căn" in clean or "nhà nguyên căn" in clean:
        res.room_type = "WHOLE_HOUSE"
    elif "studio" in clean or "căn hộ mini" in clean or "chung cư mini" in clean:
        res.room_type = "STUDIO"
    elif "sleepbox" in clean or "ký túc xá" in clean or "ktx" in clean or "giường tầng" in clean or "box" in clean:
        res.room_type = "SLEEPBOX"
    elif "chung cư" in clean or "căn hộ" in clean:
        res.room_type = "APARTMENT"
    elif "phòng trọ" in clean or "nhà trọ" in clean or "phòng" in clean:
        res.room_type = "ROOM"

    # 2. Giá
    max_m = re.search(r"(?:dưới|tối đa|khoảng|tầm|tới|dưới mức)\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
    if max_m:
        res.max_price = float(max_m.group(1).replace(",", ".")) * 1_000_000
    elif "2tr" in clean or "3tr" in clean or "4tr" in clean or "5tr" in clean:
        qm = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
        if qm:
            res.max_price = float(qm.group(1).replace(",", ".")) * 1_000_000

    range_m = re.search(r"từ\s*(\d+(?:[.,]\d+)?)\s*(?:đến|tới|-)\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
    if range_m:
        res.min_price = float(range_m.group(1).replace(",", ".")) * 1_000_000
        res.max_price = float(range_m.group(2).replace(",", ".")) * 1_000_000

    # 3. Vị trí
    loc_m = re.search(
        r"(?:ở|tại|quanh|gần|khu vực)\s+([A-Za-zÀ-ỹ0-9\s]{2,30}?)(?=\s*(?:tầm|dưới|khoảng|giá|có|phòng|$))",
        text,
        flags=re.IGNORECASE,
    )
    if loc_m:
        cand = loc_m.group(1).strip()
        if len(cand) >= 3 and cand.lower() not in ["phòng", "nhà", "trọ", "đây"]:
            res.location_text = cand

    # 4. Tiện ích (đối sánh từ khóa về thẳng mã AmenityCode)
    amenity_keywords: dict[str, list[str]] = {
        "aircon": ["máy lạnh", "điều hòa", "may lanh", "dieu hoa", "ac", "ml"],
        "mezzanine": ["gác lửng", "gác xép", "có gác", "co gac", "gác đúc", "gác", "gác lưng", "gác cao"],
        "private_wc": ["wc riêng", "vệ sinh riêng", "toilet riêng", "khép kín", "ve sinh rieng"],
        "kitchen": ["kệ bếp", "bếp riêng", "nấu ăn", "nau an", "chỗ nấu ăn", "bếp"],
        "fridge": ["tủ lạnh", "tu lanh"],
        "washing_machine": ["máy giặt", "may giat"],
        "window_balcony": ["ban công", "cửa sổ", "ban cong", "cua so", "view thoáng", "thoáng mát"],
        "furniture": ["nội thất", "full nội thất", "đầy đủ đồ", "noi that"],
        "parking": ["chỗ để xe", "hầm xe", "giữ xe", "cho de xe", "bãi xe"],
        "elevator": ["thang máy", "thang may"],
        "free_hours": ["giờ giấc tự do", "tự do", "gio tu do", "24/24", "24/7"],
        "no_shared_landlord": ["không chung chủ", "ko chung chủ", "khong chung chu", "lối đi riêng"],
        "pet_allowed": ["nuôi pet", "nuôi chó", "nuôi mèo", "thú cưng", "pet", "boss", "cho nuôi mèo", "cho nuôi pet"],
        "fingerprint_lock": ["vân tay", "khóa vân tay", "thẻ từ", "khoa van tay"],
        "camera": ["camera"],
        "guard": ["bảo vệ", "bao ve"],
        "safe_area": ["an ninh", "an toàn", "khu an ninh"],
    }
    for code, kws in amenity_keywords.items():
        for kw in kws:
            pattern = rf"(?:^|\b|\s){re.escape(kw)}(?:\b|\s|$)"
            if re.search(pattern, clean) or kw in clean:
                if code not in res.amenities:
                    res.amenities.append(code)
                break

    return res


def extract_preferences_with_llm(
    user_text: str,
    model: Any = None,
    current_pref: Optional[UserPreferenceState] = None,
) -> UserPreferenceState:
    """Sử dụng LLM để trích xuất trực tiếp mã AmenityCode và RoomType theo yêu cầu người dùng.
    Không cần từ điển map phức tạp vì LLM ánh xạ trực tiếp sang các mã canonical.
    """
    pref = current_pref.model_copy(deep=True) if current_pref else UserPreferenceState()

    extracted: Optional[ExtractedPreference] = None

    # 1. Thử gọi LLM để trích xuất thông minh
    if model is not None:
        try:
            messages = [
                SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                HumanMessage(content=user_text),
            ]
            resp = model.invoke(messages)
            raw_content = getattr(resp, "content", "")
            if isinstance(raw_content, str) and raw_content.strip():
                cleaned_json = _clean_json_response(raw_content)
                parsed = json.loads(cleaned_json)
                extracted = ExtractedPreference(**parsed)
        except Exception as e:
            logger.warning(f"Lỗi gọi LLM trích xuất tiện ích: {e}. Sử dụng bộ trích xuất dự phòng.")

    # 2. Nếu LLM không khả dụng hoặc lỗi -> Fallback
    if extracted is None:
        extracted = _fallback_extract(user_text)

    # 3. Hòa nhập dữ liệu vào UserPreferenceState
    if extracted.location_text:
        if pref.location_text and extracted.location_text.lower() != pref.location_text.lower():
            pref.lat = None
            pref.lng = None
        pref.location_text = extracted.location_text

    # Loại phòng (RoomType)
    if extracted.room_type:
        rt_clean = extracted.room_type.strip().upper()
        if rt_clean in CANONICAL_ROOM_TYPES:
            pref.room_type = rt_clean
            pref.room_type_id = ROOM_TYPE_CODE_TO_ID.get(rt_clean)

    if extracted.min_price is not None:
        pref.min_price = extracted.min_price
    if extracted.max_price is not None:
        pref.max_price = extracted.max_price
    if extracted.min_area is not None:
        pref.min_area = extracted.min_area
    if extracted.max_area is not None:
        pref.max_area = extracted.max_area

    # Chuẩn hóa tiện ích: Lưu trữ trực tiếp mã AmenityCode chuẩn hóa, không chèn nhãn tiếng Việt trùng lặp
    for a in extracted.amenities:
        clean_code = a.strip().lower()
        if clean_code in CANONICAL_AMENITIES:
            if clean_code not in pref.amenities:
                pref.amenities.append(clean_code)

    for req in extracted.special_requirements:
        if req and req not in pref.special_requirements:
            pref.special_requirements.append(req)

    return pref
