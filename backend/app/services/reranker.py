"""MCDM Dynamic Reranking Engine cho Smart Housing Search.

Đánh giá và tái xếp hạng danh sách tin phòng từ Hybrid Search theo Multi-Criteria Decision Making (MCDM):
1. Giá (price): Đánh giá mức độ hợp lý thông qua ML PriceEvaluator.
2. Vị trí (location): Haversine distance tới tọa độ mong muốn của người dùng.
3. Tiện nghi (amenity): Tỷ lệ đáp ứng các tiện ích ưu tiên mềm (canonical taxonomy 17 tiện ích).
4. An ninh (safety): Điểm an ninh tổng hợp của khu trọ.
5. Ngữ nghĩa (semantic): Điểm tương đồng ngữ nghĩa từ Dense pgvector Embedding.

Public API:
    rerank(candidates, user_pref, limit, offset, base_weights) -> [(breakdown, listing)]
    explain_match(breakdown, top_n)                           -> dict giải thích cho AI
    DEFAULT_WEIGHTS                                           -> dict trọng số cơ sở 5 tiêu chí
"""
from math import asin, cos, radians, sin, sqrt
from typing import Mapping, Optional, Sequence

__all__ = ["rerank", "explain_match", "DEFAULT_WEIGHTS"]

# --- Constants ---
UNKNOWN_SCORE: float = 0.0
EARTH_RADIUS_KM: float = 6371.0
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "location": 0.25,
    "price": 0.25,
    "safety": 0.20,
    "amenity": 0.20,
    "semantic": 0.10,
}

# --- Helpers ---
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _get(obj: object, name: str, default: object = None) -> object:
    """Đọc field từ object hoặc dict, để không phụ thuộc kiểu listing/user_pref."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _score_or_unknown(obj: object, name: str) -> float:
    value = _get(obj, name)
    if value is None:
        return UNKNOWN_SCORE
    try:
        return _clamp01(float(value)) # type: ignore
    except (ValueError, TypeError):
        return UNKNOWN_SCORE


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay giữa 2 tọa độ (Haversine formula)."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))


def _location_fit(dist_km: float, near_km: float = 0.8, far_km: float = 5.0) -> float:
    """<= near_km -> 1.0, >= far_km -> 0.0, ở giữa suy giảm phi tuyến (ratio ** 1.5)."""
    if dist_km <= near_km:
        return 1.0
    if dist_km >= far_km:
        return 0.0
    ratio = (dist_km - near_km) / (far_km - near_km)
    return max(0.0, 1.0 - (ratio ** 1.5))


def _normalize_amenity(code: object) -> str:
    """Chuẩn hoá mã tiện ích từ Enum hoặc chuỗi về canonical code chữ thường."""
    if not code:
        return ""
    val = getattr(code, "value", code)
    return str(val).strip().lower()


def _amenity_fit(
    requested: Optional[Sequence[object]] = None,
    concept_scores: Optional[Mapping[str, float]] = None,
    amenity_overall: Optional[float] = None,
    preferred: Optional[Sequence[object]] = None,
) -> float:
    """Điểm tiện ích trong MCDM Rerank (Phương án 3 - Kết hợp):
    - Tiện ích bắt buộc (requested) đã được lọc cứng (Pass/Fail) ở SQL & Grounding,
      tuyệt đối KHÔNG chấm điểm lặp lại trong MCDM.
    - Nếu có tiện ích ưu tiên mềm (preferred): tính độ thỏa mãn của preferred (70%) + tiện ích tổng thể (30%).
    - Nếu không có preferred (bật do nhấn mạnh tiện nghi tổng thể): chấm theo amenity_overall hoặc fallback 1.0.
    """
    scores = concept_scores or {}
    overall_val = (
        _clamp01(amenity_overall)
        if amenity_overall is not None
        else (_clamp01(scores["amenity_overall"]) if "amenity_overall" in scores else 1.0)
    )

    if preferred:
        norm_pref = list(dict.fromkeys(_normalize_amenity(a) for a in preferred if _normalize_amenity(a)))
        if norm_pref:
            pref_fit = sum(_clamp01(float(scores.get(a, UNKNOWN_SCORE))) for a in norm_pref) / len(norm_pref)
            return _clamp01(0.7 * pref_fit + 0.3 * overall_val)

    return overall_val


# --- Weights ---
def _dynamic_weights(user_pref: object, base: Optional[Mapping[str, float]] = None) -> dict[str, float]:
    """Chỉ giữ tiêu chí đang bật, rồi chuẩn hóa L1 để tổng trọng số = 1.0.
    - Tiện ích bắt buộc (amenities) chỉ lọc cứng ở SQL & Grounding, KHÔNG bật trọng số amenity trong MCDM.
    - Trọng số amenity chỉ bật khi có preferred_amenities, include_amenity_overall,
      hoặc khi caller chủ động truyền trọng số 'amenity' trong base_weights (khi nhấn mạnh tiện nghi tổng thể).
    """
    eff_base = base if base is not None else DEFAULT_WEIGHTS
    lat = _get(user_pref, "lat")
    lng = _get(user_pref, "lng")
    preferred_amenities = _get(user_pref, "preferred_amenities")
    include_overall = bool(_get(user_pref, "include_amenity_overall", False))
    explicit_amenity_weight = (
        base is not None
        and base is not DEFAULT_WEIGHTS
        and "amenity" in base
        and float(base.get("amenity", 0.0)) > 0
    )

    active = {
        "price": True,     # Bắt buộc: luôn đánh giá mức độ hợp lý của giá phòng (price_score từ ML)
        "safety": True,    # Bắt buộc: luôn đánh giá điểm an ninh (safety_score)
        "semantic": True,  # Bắt buộc: luôn đánh giá độ khớp ngữ nghĩa (similarity_score)
        "location": lat is not None and lng is not None,  # Động: chỉ bật khi có toạ độ mục tiêu
        "amenity": bool(preferred_amenities) or include_overall or explicit_amenity_weight,
    }
    w = {k: float(eff_base.get(k, DEFAULT_WEIGHTS.get(k, 0.2))) for k, on in active.items() if on}
    total = sum(w.values())
    if total <= 0:
        raise ValueError("Tổng trọng số của các tiêu chí đang bật phải > 0")
    return {k: v / total for k, v in w.items()}


# --- Scoring ---
def _location_part(listing: object, user_pref: object) -> float:
    orm = _get(listing, "listing", listing)
    lat = _get(orm, "lat")
    lng = _get(orm, "lng")
    pref_lat = _get(user_pref, "lat")
    pref_lng = _get(user_pref, "lng")

    if lat is None or lng is None or pref_lat is None or pref_lng is None:
        return UNKNOWN_SCORE

    try:
        dist = _haversine_km(float(lat), float(lng), float(pref_lat), float(pref_lng)) # type: ignore
        max_dist = _get(user_pref, "max_distance_km")
        far_km = float(max_dist) if max_dist else 5.0
        return _location_fit(dist, near_km=0.8, far_km=far_km)
    except (ValueError, TypeError):
        return UNKNOWN_SCORE


def _price_fit(orm: object, user_pref: object = None, weights: Optional[Mapping[str, float]] = None) -> float:
    """Điểm hợp lý giá (price_score) do mô hình Machine Learning thẩm định kết hợp độ rẻ tiền danh nghĩa."""
    price_score = _get(orm, "price_score")
    ml_score = 0.50
    if price_score is not None:
        try:
            ml_score = _clamp01(float(price_score)) # type: ignore
        except (ValueError, TypeError):
            pass

    max_price = _get(user_pref, "max_price") if user_pref else None
    price_vnd = _get(orm, "price_vnd")
    if max_price and price_vnd and float(max_price) > 0:
        p_val = float(price_vnd)
        m_val = float(max_price)
        if p_val <= m_val:
            savings_ratio = max(0.0, min(1.0, (m_val - p_val) / m_val))

            # Xác định người dùng có đang ưu tiên giá rẻ danh nghĩa hay không
            prefer_cheap = False
            if user_pref:
                if _get(user_pref, "prefer_cheapest"):
                    prefer_cheap = True
                user_weights = _get(user_pref, "weights")
                if isinstance(user_weights, Mapping) and float(user_weights.get("price", 0.0)) > 0.28:
                    prefer_cheap = True
            if weights and float(weights.get("price", 0.0)) > 0.28:
                prefer_cheap = True

            if prefer_cheap:
                # Đẩy tỷ trọng độ rẻ tiền thực tế (savings_ratio) lên 85%, ML score chỉ 15%
                return _clamp01(0.85 * (0.3 + 0.7 * savings_ratio) + 0.15 * ml_score)
            else:
                # Cân bằng 50% độ rẻ tiền + 50% độ hợp lý thị trường từ ML
                return _clamp01(0.50 * ml_score + 0.50 * (0.4 + 0.6 * savings_ratio))
        else:
            return _clamp01(0.3 * ml_score)

    return ml_score


def _match_breakdown(
    listing: object,
    user_pref: object,
    weights: dict[str, float],
) -> dict[str, object]:
    """Tính điểm từng thành phần dựa trên weights đã pre-computed theo mô hình MCDM."""
    orm = _get(listing, "listing", listing)
    scorers = {
        "price": lambda: _price_fit(orm, user_pref, weights=weights),
        "safety": lambda: _score_or_unknown(orm, "safety_score"),
        "location": lambda: _location_part(listing, user_pref),
        "amenity": lambda: _amenity_fit(
            _get(user_pref, "amenities"), # type: ignore
            _get(orm, "concept_scores"), # type: ignore
            _get(orm, "amenity_overall"), # type: ignore
            preferred=_get(user_pref, "preferred_amenities"), # type: ignore
        ),
        "semantic": lambda: _score_or_unknown(listing, "similarity_score") if isinstance(listing, Mapping) and "similarity_score" in listing else _score_or_unknown(orm, "similarity_score"),
    }
    parts: dict[str, float] = {k: scorers[k]() for k in weights}
    contributions: dict[str, float] = {k: weights[k] * parts[k] for k in parts}
    return {
        "score": sum(contributions.values()),
        "parts": parts,
        "weights": weights,
        "contributions": contributions,
    }


# --- Public API ---
def rerank(
    candidates: list[object],
    user_pref: object,
    limit: int = 5,
    offset: int = 0,
    base_weights: Optional[Mapping[str, float]] = None,
) -> list[tuple[dict[str, object], object]]:
    """Xếp hạng candidates (từ vector search). Trả về [(breakdown, listing)] đã sort giảm dần."""
    if not candidates:
        return []

    effective_weights = base_weights or DEFAULT_WEIGHTS
    computed_weights = _dynamic_weights(user_pref, effective_weights)

    scored = [(_match_breakdown(c, user_pref, computed_weights), c) for c in candidates]
    scored.sort(
        key=lambda x: (
            round(float(x[0]["score"]), 8), # type: ignore
            str(_get(_get(x[1], "listing", x[1]), "id", "")),
        ),
        reverse=True,
    )
    return scored[offset : offset + limit]


def explain_match(breakdown: dict[str, object], top_n: int = 5) -> dict[str, object]:
    """Rút gọn breakdown thành dữ liệu để đưa cho AI giải thích 'vì sao phòng này cao'."""
    parts: dict[str, float] = breakdown["parts"] # type: ignore
    weights: dict[str, float] = breakdown["weights"] # type: ignore
    contrib: dict[str, float] = breakdown["contributions"] # type: ignore
    top = sorted(contrib, key=lambda k: contrib[k], reverse=True)[:top_n]
    return {
        "score": round(float(breakdown["score"]), 3), # type: ignore
        "top_factors": [
            {
                "name": k,
                "fit": round(parts[k], 2),
                "weight": round(weights[k], 2),
                "contribution": round(contrib[k], 3),
            }
            for k in top
        ],
        "weak_factors": [k for k, v in parts.items() if v < 0.4],
        "unknown": [k for k, v in parts.items() if v == UNKNOWN_SCORE],
    }
