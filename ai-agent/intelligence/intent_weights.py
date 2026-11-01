"""Intent-aware dynamic weighting (MCDM).

Nhận mức ưu tiên định tính từ NLU (`Priorities` -> `apply_priorities`), kết hợp quy tắc kích hoạt động
theo trạng thái tiêu chí (`UserPreferenceState`) và chuẩn hoá L1 (tổng trọng số = 1.0).
"""

from __future__ import annotations

from typing import Mapping, Optional

from domain.schemas import UserPreferenceState
from intelligence.nlu import CRITERIA  # noqa: F401

DEFAULT_BASE_WEIGHTS = {"price": 1.0, "safety": 1.0, "semantic": 1.0, "location": 1.0, "amenity": 1.0}


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
        for _ in (None,)
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
