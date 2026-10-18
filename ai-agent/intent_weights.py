"""Module Intent-Aware Dynamic Weighting: Tính toán trọng số thích ứng theo ý định người dùng.
Phục vụ mô hình Adaptive Multi-Criteria Decision Making (MCDM) cho Smart Housing Decision Support System.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional
from schemas import UserPreferenceState

# Trọng số nền cơ sở
DEFAULT_BASE_WEIGHTS = {
    "price": 1.0,
    "safety": 1.0,
    "semantic": 1.0,
    "location": 1.0,
    "amenity": 1.0,
}

# Mẫu nhận diện ý định ưu tiên (Intent Boosters)
PRICE_BOOST_PATTERNS = [
    r"rẻ\s*nhất",
    r"giá\s*rẻ",
    r"tiết\s*kiệm",
    r"ngân\s*sách\s*(?:hẹp|thấp|eo\s*hẹp)",
    r"kinh\s*tế",
    r"ít\s*tiền",
    r"hạt\s*dẻ",
    r"rẻ\s*nữa",
    r"rẻ\s*hơn",
    r"mềm\s*nhất",
]

LOCATION_BOOST_PATTERNS = [
    r"sát\s*(?:bên|nách)",
    r"đi\s*bộ\s*được",
    r"ngay\s*cạnh",
    r"rất\s*gần",
    r"sát\s*trường",
    r"bán\s*kính\s*gần",
    r"càng\s*gần\s*càng\s*tốt",
    r"gần\s*nhất",
    r"gần\s*uit",
]

SAFETY_BOOST_PATTERNS = [
    r"an\s*ninh",
    r"an\s*toàn",
    r"nữ\s*ở\s*một\s*mình",
    r"sợ\s*trộm",
    r"khóa\s*vân\s*tay",
    r"bảo\s*vệ",
    r"camera",
    r"yên\s*tâm",
]

AMENITY_BOOST_PATTERNS = [
    r"full\s*nội\s*thất",
    r"đầy\s*đủ\s*đồ",
    r"tiện\s*nghi\s*cao",
    r"nội\s*thất\s*(?:xịn|cao\s*cấp|đẹp)",
    r"đủ\s*tiện\s*nghi",
    r"có\s*gác",
    r"gác\s*(?:lửng|cao|lưng|lững|đúc|xép|gỗ)",
    r"máy\s*lạnh",
    r"điều\s*hòa",
    r"nuôi\s*(?:chó|mèo|pet|thú\s*cưng)",
]


def detect_intent_multipliers(
    user_text: str,
    accumulated_multipliers: Optional[dict[str, float]] = None,
) -> tuple[dict[str, float], list[str]]:
    """Phát hiện ý định người dùng và trả về dict hệ số nhân ưu tiên (multipliers) kèm lời giải thích."""
    clean = user_text.lower()
    multipliers = dict(accumulated_multipliers or {"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0})
    explanations: list[str] = []

    # 1. Kiểm tra ưu tiên giá
    if any(re.search(p, clean) for p in PRICE_BOOST_PATTERNS):
        multipliers["price"] = 2.0
        explanations.append("ưu tiên mức giá rẻ/tiết kiệm (boost 2.0x)")

    # 2. Kiểm tra ưu tiên khoảng cách/vị trí
    if any(re.search(p, clean) for p in LOCATION_BOOST_PATTERNS):
        multipliers["location"] = 2.0
        explanations.append("ưu tiên vị trí gần điểm mục tiêu (boost 2.0x)")

    # 3. Kiểm tra ưu tiên an ninh
    if any(re.search(p, clean) for p in SAFETY_BOOST_PATTERNS):
        multipliers["safety"] = 2.0
        explanations.append("ưu tiên khu vực an ninh/an toàn cao (boost 2.0x)")

    # 4. Kiểm tra ưu tiên tiện nghi
    if any(re.search(p, clean) for p in AMENITY_BOOST_PATTERNS):
        multipliers["amenity"] = 1.8
        explanations.append("ưu tiên đầy đủ tiện nghi/nội thất (boost 1.8x)")

    return multipliers, explanations


def compute_normalized_weights(
    preferences: UserPreferenceState,
    multipliers: dict[str, float],
    base_weights: Optional[Mapping[str, float]] = None,
) -> dict[str, float]:
    """Tính toán vector trọng số chuẩn hoá (L1 Normalization sao cho tổng = 1.0).

    Quy tắc kích hoạt tiêu chí:
    - price, safety, semantic: LUÔN BẮT BUỘC (True)
    - location: ĐỘNG (chỉ bật khi có toạ độ lat, lng hoặc location_text)
    - amenity: ĐỘNG (chỉ bật khi người dùng yêu cầu tiện ích cụ thể)
    """
    base = base_weights or DEFAULT_BASE_WEIGHTS

    has_location = bool((preferences.lat is not None and preferences.lng is not None) or preferences.location_text)
    has_amenities = bool(preferences.amenities)

    active = {
        "price": True,
        "safety": True,
        "semantic": True,
        "location": has_location,
        "amenity": has_amenities,
    }

    raw_scores = {}
    for k, is_on in active.items():
        if is_on:
            raw_scores[k] = base.get(k, 1.0) * multipliers.get(k, 1.0)

    total = sum(raw_scores.values())
    if total <= 0:
        return {k: round(1.0 / len(raw_scores), 4) for k in raw_scores}

    return {k: round(v / total, 4) for k, v in raw_scores.items()}
