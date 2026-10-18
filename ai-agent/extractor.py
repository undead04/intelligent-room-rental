"""Module trích xuất nhu cầu và tiện ích bằng LLM (LLM-based Preference & Amenity Extraction).
Cung cấp danh mục tiện ích chuẩn (Amenity Catalog) cho LLM để mô hình ngôn ngữ tự động hiểu
ngữ cảnh, từ lóng, phương ngữ và viết tắt tiếng Việt của người dùng.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from schemas import UserPreferenceState

logger = logging.getLogger(__name__)

# Danh mục 16 tiện ích chuẩn kèm định nghĩa ngữ nghĩa phục vụ LLM
AMENITY_CATALOG: dict[str, str] = {
    "mezzanine": "Gác lửng, gác xép, gác cao, gác lưng, gác lững, gác đúc, gác gỗ, có gác, phòng có gác",
    "aircon": "Máy lạnh, điều hòa, máy điều hòa, ac, ml",
    "private_wc": "WC riêng, vệ sinh riêng, toilet riêng, toilet trong phòng, vệ sinh khép kín, phòng tắm riêng",
    "kitchen": "Kệ bếp, bếp riêng, khu bếp, nấu ăn, cho nấu ăn, chỗ nấu ăn, nấu nướng",
    "fridge": "Tủ lạnh",
    "washing_machine": "Máy giặt, chỗ giặt đồ",
    "window_balcony": "Ban công, cửa sổ, phòng thoáng mát, view thoáng, ánh sáng tự nhiên, lô gia",
    "furniture": "Nội thất, full nội thất, giường, nệm, tủ quần áo, bàn ghế, đầy đủ đồ",
    "pet_allowed": "Cho nuôi thú cưng, nuôi chó, nuôi mèo, nuôi pet, thú cưng, cho nuôi pet, boss",
    "parking": "Chỗ để xe, giữ xe, nhà xe, bãi xe, hầm để xe",
    "elevator": "Thang máy",
    "free_hours": "Giờ giấc tự do, giờ tự do, 24/24, 24/7, ra vào tự do, không chung cổng giới nghiêm",
    "no_shared_landlord": "Không chung chủ, không ở chung chủ, ko chung chủ, lối đi riêng, tự do riêng tư",
    "fingerprint_lock": "Khóa vân tay, thẻ từ, khóa thông minh, smart lock, cổng vân tay",
    "security": "Bảo vệ, bảo vệ 24/7, an ninh tốt, camera an ninh, an ninh đảm bảo",
    "wifi": "Wifi, internet miễn phí, mạng cáp quang",
}

CANONICAL_AMENITIES = set(AMENITY_CATALOG.keys())

CANONICAL_TO_LABEL: dict[str, str] = {
    "mezzanine": "gác lửng",
    "aircon": "máy lạnh",
    "private_wc": "wc riêng",
    "kitchen": "kệ bếp",
    "fridge": "tủ lạnh",
    "washing_machine": "máy giặt",
    "window_balcony": "ban công",
    "furniture": "nội thất",
    "pet_allowed": "nuôi thú cưng",
    "parking": "chỗ để xe",
    "elevator": "thang máy",
    "free_hours": "giờ giấc tự do",
    "no_shared_landlord": "không chung chủ",
    "fingerprint_lock": "khoá vân tay",
    "security": "bảo vệ",
    "wifi": "wifi",
}

EXTRACTION_SYSTEM_PROMPT = """Bạn là trợ lý AI chuyên trích xuất tiêu chí tìm kiếm phòng trọ cho hệ thống Homigo.
Nhiệm vụ của bạn là đọc câu nói của người dùng và trích xuất các tiêu chí tìm phòng dưới dạng JSON duy nhất.

DANH MỤC TIỆN ÍCH CHUẨN (AMENITY CATALOG):
- mezzanine: Gác lửng, gác xép, gác cao, gác lưng, gác lững, gác đúc, gác gỗ, có gác...
- aircon: Máy lạnh, điều hòa, máy điều hòa, ac, ml...
- private_wc: WC riêng, vệ sinh riêng, toilet riêng, khép kín, toilet trong phòng...
- kitchen: Kệ bếp, bếp riêng, khu bếp, nấu ăn, cho nấu ăn, chỗ nấu ăn...
- fridge: Tủ lạnh...
- washing_machine: Máy giặt, chỗ giặt đồ...
- window_balcony: Ban công, cửa sổ, phòng thoáng mát, view thoáng, ánh sáng tự nhiên...
- furniture: Nội thất, full nội thất, giường, nệm, tủ quần áo, bàn ghế...
- pet_allowed: Cho nuôi thú cưng, nuôi chó, nuôi mèo, nuôi pet, boss...
- parking: Chỗ để xe, giữ xe, nhà xe, bãi xe, hầm để xe...
- elevator: Thang máy...
- free_hours: Giờ giấc tự do, 24/24, ra vào tự do, không giới nghiêm...
- no_shared_landlord: Không chung chủ, không ở chung chủ, lối đi riêng, tự do riêng tư...
- fingerprint_lock: Khóa vân tay, thẻ từ, khóa thông minh...
- security: Bảo vệ, bảo vệ 24/7, camera, an ninh tốt...
- wifi: Wifi, internet...

QUY TẮC TRÍCH XUẤT:
1. `location_text`: Tên địa điểm, khu vực, quận huyện, phường xã hoặc trường học/công ty người dùng muốn tìm. Nếu không nhắc thì để null.
2. `min_price`: Mức giá tối thiểu bằng số VNĐ (ví dụ: 'từ 2 triệu' -> 2000000). Nếu không có để null.
3. `max_price`: Mức giá tối đa bằng số VNĐ (ví dụ: 'tầm 5 triệu đổ xuống' -> 5000000, 'dưới 3.5tr' -> 3500000). Nếu không có để null.
4. `amenities`: Mảng danh sách các mã canonical tiện ích được người dùng yêu cầu. CHỈ ĐƯỢC CHỌN từ 16 mã chuẩn ở trên (ví dụ: ['mezzanine', 'aircon']).
   - Tự động hiểu tiếng Việt linh hoạt: 'gác lưng', 'có gác' -> 'mezzanine'; 'ml' -> 'aircon'; 'boss', 'mèo' -> 'pet_allowed'.
5. `special_requirements`: Mảng các yêu cầu mềm khác như 'yên tĩnh', 'sạch sẽ', 'đường không ngập'.

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC (Chỉ trả về JSON thuần):
{
  "location_text": null,
  "min_price": null,
  "max_price": null,
  "min_area": null,
  "max_area": null,
  "amenities": [],
  "special_requirements": []
}"""


class ExtractedPreference(BaseModel):
    location_text: Optional[str] = None
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
    # Tìm chuỗi json bắt đầu bằng { và kết thúc bằng }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _fallback_extract(text: str) -> ExtractedPreference:
    """Bộ trích xuất dự phòng nhẹ khi LLM không khả dụng (offline / mock)."""
    clean = text.lower()
    res = ExtractedPreference()

    # Giá
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

    # Vị trí
    loc_m = re.search(
        r"(?:ở|tại|quanh|gần|khu vực)\s+([A-Za-zÀ-ỹ0-9\s]{2,30}?)(?=\s*(?:tầm|dưới|khoảng|giá|có|phòng|$))",
        text,
        flags=re.IGNORECASE,
    )
    if loc_m:
        cand = loc_m.group(1).strip()
        if len(cand) >= 3 and cand.lower() not in ["phòng", "nhà", "trọ", "đây"]:
            res.location_text = cand

    # Tiện ích
    for code, desc in AMENITY_CATALOG.items():
        kws = [k.strip().lower() for k in desc.split(",")]
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
    """Sử dụng LLM kết hợp Amenity Catalog để trích xuất có cấu trúc tiêu chí người dùng.
    Tự động hòa nhập (merge) vào trạng thái tiêu chí hiện tại.
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
        # Nếu đổi địa điểm khác -> reset lat, lng cũ để geocode lại
        if pref.location_text and extracted.location_text.lower() != pref.location_text.lower():
            pref.lat = None
            pref.lng = None
        pref.location_text = extracted.location_text

    if extracted.min_price is not None:
        pref.min_price = extracted.min_price
    if extracted.max_price is not None:
        pref.max_price = extracted.max_price
    if extracted.min_area is not None:
        pref.min_area = extracted.min_area
    if extracted.max_area is not None:
        pref.max_area = extracted.max_area

    # Chuẩn hóa amenities: hỗ trợ cả mã canonical và nhãn tiếng Việt
    for a in extracted.amenities:
        canonical = a.strip().lower()
        if canonical in CANONICAL_AMENITIES:
            label = CANONICAL_TO_LABEL.get(canonical, canonical)
            if canonical not in pref.amenities:
                pref.amenities.append(canonical)
            if label not in pref.amenities:
                pref.amenities.append(label)
        elif canonical:
            # Nếu LLM trả về nhãn tiếng Việt (ví dụ 'gác lửng'), kiểm tra qua catalog
            for code, desc in AMENITY_CATALOG.items():
                if canonical in desc.lower():
                    label = CANONICAL_TO_LABEL.get(code, code)
                    if code not in pref.amenities:
                        pref.amenities.append(code)
                    if label not in pref.amenities:
                        pref.amenities.append(label)
                    break

    for req in extracted.special_requirements:
        if req and req not in pref.special_requirements:
            pref.special_requirements.append(req)

    return pref
