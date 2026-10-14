"""Rerank danh sách tin phòng theo user preference.

Public API:
    rerank(candidates, user_pref, limit, offset) -> [(breakdown, listing)]
    explain_match(breakdown, top_n)              -> dict gọn để đưa cho AI giải thích
    component_influence(listings, prefs)         -> chẩn đoán offline (tune trọng số)
"""
from math import asin, cos, radians, sin, sqrt
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

__all__ = ["rerank", "explain_match", "component_influence", "DEFAULT_WEIGHTS"]

# --- Constants ---
UNKNOWN_SCORE = 0.4
EARTH_RADIUS_KM = 6371.0
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "price": 0.2,
    "location": 0.2,
    "amenity": 0.2,
    "safety": 0.2,
    "semantic": 0.2,
}


# --- Helpers ---
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Đọc field từ object hoặc dict, để không phụ thuộc kiểu listing/user_pref."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _score_or_unknown(obj: Any, name: str) -> float:
    value = _get(obj, name)
    return UNKNOWN_SCORE if value is None else _clamp01(value)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay giữa 2 tọa độ."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))


def _location_fit(dist_km: float, near_km: float = 1.0, far_km: float = 10.0) -> float:
    """<= near_km -> 1.0, >= far_km -> 0.0, ở giữa giảm tuyến tính."""
    if dist_km <= near_km:
        return 1.0
    if dist_km >= far_km:
        return 0.0
    return 1.0 - (dist_km - near_km) / (far_km - near_km)


def _amenity_fit(requested: Sequence[str] | None, concept_scores: Mapping | None) -> float:
    """Điểm trung bình của các tiện ích user yêu cầu (thiếu dữ liệu -> trung tính)."""
    if not requested:
        return 1.0
    scores = concept_scores or {}
    return sum(_clamp01(scores.get(a, UNKNOWN_SCORE)) for a in requested) / len(requested)


# --- Weights ---
def _dynamic_weights(user_pref: Any, base: Mapping[str, float]) -> dict[str, float]:
    """Chỉ giữ tiêu chí user có nói tới, rồi chuẩn hóa để tổng = 1."""
    lat = _get(user_pref, "lat")
    lng = _get(user_pref, "lng")
    amenities = _get(user_pref, "amenities")
    query = _get(user_pref, "query")

    active = {
        "price": True,     # Bắt buộc: luôn đánh giá giá phòng
        "safety": True,    # Bắt buộc: luôn đánh giá điểm an ninh
        "semantic": True,  # Bắt buộc: luôn đánh giá độ khớp ngữ nghĩa
        "location": lat is not None and lng is not None,  # Động: chỉ bật khi có toạ độ
        "amenity": bool(amenities),                       # Động: chỉ bật khi user yêu cầu tiện ích cụ thể
    }
    w = {k: base[k] for k, on in active.items() if on}
    total = sum(w.values())
    if total <= 0:
        raise ValueError("Tổng trọng số của các tiêu chí đang bật phải > 0")
    return {k: v / total for k, v in w.items()}


# --- Scoring ---
def _location_part(listing: Any, user_pref: Any) -> float:
    orm = _get(listing, "listing", listing)
    lat, lng = _get(orm, "lat"), _get(orm, "lng")
    pref_lat, pref_lng = _get(user_pref, "lat"), _get(user_pref, "lng")

    if lat is None or lng is None or pref_lat is None or pref_lng is None:
        return UNKNOWN_SCORE

    return _location_fit(_haversine_km(lat, lng, pref_lat, pref_lng))


def _match_breakdown(
    listing: dict[str, Any] | Any,
    user_pref: Any,
    weights: dict[str, float],
) -> dict:
    """Tính điểm từng thành phần dựa trên weights đã pre-computed."""
    orm = _get(listing, "listing", listing)
    scorers = {
        "price": lambda: _score_or_unknown(orm, "price_score"),
        "safety": lambda: _score_or_unknown(orm, "safety_score"),
        "location": lambda: _location_part(listing, user_pref),
        "amenity": lambda: _amenity_fit(_get(user_pref, "amenities"), _get(orm, "concept_scores")),
        "semantic": lambda: _score_or_unknown(listing, "similarity_score") if isinstance(listing, Mapping) and "similarity_score" in listing else _score_or_unknown(orm, "similarity_score"),
    }
    parts = {k: scorers[k]() for k in weights}
    contributions = {k: weights[k] * parts[k] for k in parts}
    return {
        "score": sum(contributions.values()),
        "parts": parts,
        "weights": weights,
        "contributions": contributions,
    }


# --- Public API ---
def rerank(
    candidates: list[dict[str, Any] | Any],
    user_pref: Any,
    limit: int = 5,
    offset: int = 0,
    base_weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> list[tuple[dict, Any]]:
    """Xếp hạng candidates (từ vector search). Trả về [(breakdown, listing)] đã sort giảm dần."""
    if not candidates:
        return []

    # OPTIMIZATION: Tính trọng số động ONCE per search request thay vì per candidate
    computed_weights = _dynamic_weights(user_pref, base_weights)

    scored = [(_match_breakdown(c, user_pref, computed_weights), c) for c in candidates]
    scored.sort(key=lambda x: x[0]["score"], reverse=True)
    return scored[offset : offset + limit]


def explain_match(breakdown: dict, top_n: int = 5) -> dict:
    """Rút gọn breakdown thành dữ liệu để đưa cho AI giải thích 'vì sao phòng này cao'."""
    parts, weights, contrib = breakdown["parts"], breakdown["weights"], breakdown["contributions"]
    top = sorted(contrib, key=contrib.get, reverse=True)[:top_n]
    return {
        "score": round(breakdown["score"], 3),
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


def component_influence(
    listings: Sequence[Any],
    prefs: Sequence[Any],
    base_weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> dict:
    """Chẩn đoán offline: ảnh hưởng thực của mỗi thành phần ~ trọng số x độ lệch chuẩn."""
    if not listings or not prefs:
        return {}
    stds: dict[str, list[float]] = {}
    ws: dict[str, list[float]] = {}
    for pref in prefs:
        computed_weights = _dynamic_weights(pref, base_weights)
        bds = [_match_breakdown(l, pref, computed_weights) for l in listings]
        for k in bds[0]["parts"]:
            stds.setdefault(k, []).append(pstdev(b["parts"][k] for b in bds))
            ws.setdefault(k, []).append(bds[0]["weights"][k])
    out = {k: {"weight": mean(ws[k]), "std": mean(stds[k])} for k in stds}
    total = sum(v["weight"] * v["std"] for v in out.values()) or 1.0
    for v in out.values():
        v["influence"] = v["weight"] * v["std"] / total
    return out