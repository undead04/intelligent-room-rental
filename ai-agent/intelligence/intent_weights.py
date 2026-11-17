"""Intent-aware dynamic weighting (MCDM).

Nhận mức ưu tiên định tính từ NLU (`Priorities` -> `apply_priorities`), kết hợp quy tắc kích hoạt động
theo trạng thái tiêu chí (`UserPreferenceState`) và chuẩn hoá L1 (tổng trọng số = 1.0).
"""

from __future__ import annotations

from typing import Mapping, Optional

from domain.enums import Amenity, normalize_amenities
from domain.schemas import UserPreferenceState

# Đồng bộ chuẩn 5 trụ cột với Backend (reranker.DEFAULT_WEIGHTS): semantic luôn có trọng số cơ sở thấp nhất (0.10)
DEFAULT_BASE_WEIGHTS = {"location": 0.25, "price": 0.25, "safety": 0.20, "amenity": 0.20, "semantic": 0.10}
BASELINE_AMENITY_SCALE = 0.5
SAFETY_AMENITIES = frozenset({
    Amenity.SAFE_AREA,
    Amenity.CAMERA,
    Amenity.GUARD,
    Amenity.FINGERPRINT_LOCK,
})


def _has_safety_signal(
    preferences: UserPreferenceState,
    multipliers: Mapping[str, float],
    base_weights: Optional[Mapping[str, float]] = None,
) -> bool:
    """Chỉ bật trụ cột safety khi người dùng nhắc tới an ninh/an toàn (hoặc caller truyền custom safety > 0)."""
    if multipliers.get("safety", 1.0) > 1.0:
        return True
    all_amenities = set(normalize_amenities(preferences.amenities)) | set(
        normalize_amenities(preferences.preferred_amenities)
    )
    if all_amenities & SAFETY_AMENITIES:
        return True
    if base_weights is not None and base_weights is not DEFAULT_BASE_WEIGHTS:
        return float(base_weights.get("safety", 0.0)) > 0.0
    return False


def compute_normalized_weights(
    preferences: UserPreferenceState,
    multipliers: dict[str, float],
    base_weights: Optional[Mapping[str, float]] = None,
    digits: int = 2,
) -> dict[str, float]:
    """Vector trọng số chuẩn hoá L1 (tổng = 1.0).

    - price, semantic, amenity: luôn bật (amenity ở mức nền nhẹ nếu chưa nêu tiện ích mềm).
    - location: chỉ bật khi có toạ độ điểm mốc.
    - safety: chỉ bật khi người dùng nhắc tới an ninh/an toàn (`multipliers['safety'] > 1.0`,
      có tiện ích an ninh trong amenities/preferred_amenities, hoặc custom base_weights có safety > 0).
    """
    base = base_weights or DEFAULT_BASE_WEIGHTS
    has_explicit_amenity = bool(preferences.preferred_amenities) or multipliers.get("amenity", 1.0) > 1.0
    amenity_active = has_explicit_amenity or (base_weights is None) or ("amenity" in base)
    safety_active = _has_safety_signal(preferences, multipliers, base_weights)

    active = {
        "price": True,
        "safety": safety_active,
        "semantic": True,
        "location": preferences.has_point,
        "amenity": amenity_active,
    }

    raw: dict[str, float] = {}
    for k, on in active.items():
        if not on:
            continue
        val = max(0.0, base.get(k, 1.0) * multipliers.get(k, 1.0))
        if k == "amenity" and not has_explicit_amenity:
            val *= BASELINE_AMENITY_SCALE
        raw[k] = val

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
