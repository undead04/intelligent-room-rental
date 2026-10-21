"""Intent-aware dynamic weighting (MCDM).

Bản này: compute_normalized_weights dùng UserPreferenceState.has_point; _strip_accents -> utils.text.
`detect_intent_multipliers` GIỮ NGUYÊN hành vi cũ nhưng chỉ còn là FALLBACK khi analyze_turn (nlu.py) lỗi;
sẽ được thay bằng Priorities.to_multipliers() ở bước 2.
"""

from __future__ import annotations

from typing import Mapping, Optional

from domain.schemas import UserPreferenceState
from utils.text import strip_accents

DEFAULT_BASE_WEIGHTS = {"price": 1.0, "safety": 1.0, "semantic": 1.0, "location": 1.0, "amenity": 1.0}
CRITERIA = ("price", "location", "safety", "amenity", "semantic")


def detect_intent_multipliers(
    user_text: str,
    accumulated_multipliers: Optional[dict[str, float]] = None,
) -> tuple[dict[str, float], list[str]]:
    """[FALLBACK] Phát hiện ý định bằng từ khoá (hành vi cũ)."""
    clean = strip_accents(user_text)
    multipliers = dict(accumulated_multipliers or {k: 1.0 for k in CRITERIA})
    explanations: list[str] = []

    price_kws = ("re nhat", "gia re", "tiet kiem", "ngan sach hep", "kinh te", "it tien", "hat de", "re nua", "re hon", "mem nhat", "gia sinh vien")
    if any(kw in clean for kw in price_kws) and not any(neg in clean for neg in ("khong can re", "ko can gia re")):
        multipliers["price"] = 2.0
        explanations.append("ưu tiên mức giá rẻ/tiết kiệm")

    loc_kws = ("sat ben", "sat nach", "di bo duoc", "di bo", "ngay canh", "rat gan", "gan nhat", "cang gan cang tot", "gan kcn", "gan truong", "gan uit", "gan ktx", "tien di lam", "thuan tien di lam")
    if any(kw in clean for kw in loc_kws):
        multipliers["location"] = 2.0
        explanations.append("ưu tiên vị trí gần điểm mục tiêu")

    safety_kws = ("an ninh", "an toan", "nu o mot minh", "khoa van tay", "bao ve", "camera", "yen tam")
    if any(kw in clean for kw in safety_kws) and not any(neg in clean for neg in ("khong can an ninh", "ko can an ninh")):
        multipliers["safety"] = 2.0
        explanations.append("ưu tiên khu vực an ninh/an toàn cao")

    amenity_kws = ("full noi that", "day du do", "tien nghi cao", "noi that xin", "noi that dep", "nhieu noi that", "noi that day du")
    if any(kw in clean for kw in amenity_kws):
        multipliers["amenity"] = 1.8
        explanations.append("ưu tiên đầy đủ tiện nghi/nội thất")

    return multipliers, explanations


def compute_normalized_weights(
    preferences: UserPreferenceState,
    multipliers: dict[str, float],
    base_weights: Optional[Mapping[str, float]] = None,
    digits: int = 2,
) -> dict[str, float]:
    """Vector trọng số chuẩn hoá L1 (tổng = 1.0).

    price, safety, semantic: luôn bật. location: chỉ khi có toạ độ.
    amenity: CHỈ bật khi có tiện ích ưu tiên mềm (preferred_amenities) hoặc khi người dùng
    nhấn mạnh mức độ tiện nghi tổng thể (multipliers['amenity'] > 1.0).
    Nếu chỉ có tiện ích bắt buộc (amenities) thì tắt vì đã lọc cứng tại SQL & Grounding.
    Tiêu chí tắt thì KHÔNG có khoá trong kết quả.
    """
    base = base_weights or DEFAULT_BASE_WEIGHTS
    amenity_active = bool(preferences.preferred_amenities) or multipliers.get("amenity", 1.0) > 1.0

    active = {
        "price": True,
        "safety": True,
        "semantic": True,
        "location": preferences.has_point,
        "amenity": amenity_active,
    }

    raw = {
        k: max(0.0, base.get(k, 1.0) * multipliers.get(k, 1.0))
        for k, on in active.items()
        if on
    }

    total = sum(raw.values())
    if total <= 0:                       # tất cả bằng 0 -> chia đều
        raw = {k: 1.0 for k in raw}
        total = float(len(raw))

    weights = {k: round(v / total, digits) for k, v in raw.items()}
    # Bù phần dư làm tròn vào trọng số lớn nhất (giữ tổng chuẩn xác 1.00)
    drift = round(1.0 - sum(weights.values()), digits)
    if drift:
        max_k = max(weights, key=weights.get)
        weights[max_k] = round(weights[max_k] + drift, digits)
    return weights
