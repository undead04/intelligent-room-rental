"""MCDM Dynamic Reranking Engine cho Smart Housing Search.

Đánh giá và tái xếp hạng danh sách tin phòng từ Hybrid Search theo Multi-Criteria Decision Making (MCDM):
1. Giá (price): Đánh giá mức độ hợp lý thông qua ML PriceEvaluator.
2. Vị trí (location): Haversine distance tới tọa độ mong muốn của người dùng.
3. Tiện nghi (amenity): Tỷ lệ đáp ứng các tiện ích bắt buộc / mong muốn (với alias mapping).
4. An ninh (safety): Điểm an ninh tổng hợp của khu trọ.
5. Ngữ nghĩa (semantic): Điểm tương đồng ngữ nghĩa từ Dense pgvector Embedding.

Public API:
    rerank(candidates, user_pref, limit, offset, base_weights) -> [(breakdown, listing)]
    explain_match(breakdown, top_n)                           -> dict giải thích cho AI
    component_influence(listings, prefs, base_weights)        -> chẩn đoán trọng số
    DEFAULT_WEIGHTS                                           -> dict trọng số cơ sở 5 tiêu chí
"""
from math import asin, cos, radians, sin, sqrt
from statistics import mean, pstdev
from typing import Mapping, Optional, Sequence

__all__ = ["rerank", "explain_match", "component_influence", "DEFAULT_WEIGHTS"]

# --- Constants ---
UNKNOWN_SCORE: float = 0.0
EARTH_RADIUS_KM: float = 6371.0
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


def _location_fit(dist_km: float, near_km: float = 1.0, far_km: float = 10.0) -> float:
    """<= near_km -> 1.0, >= far_km -> 0.0, ở giữa giảm tuyến tính."""
    if dist_km <= near_km:
        return 1.0
    if dist_km >= far_km:
        return 0.0
    return 1.0 - (dist_km - near_km) / (far_km - near_km)


_ALIAS_MAP: dict[str, str] = {
    "ac": "aircon",
    "air_conditioner": "aircon",
    "may_lanh": "aircon",
    "máy lạnh": "aircon",
    "dieu_hoa": "aircon",
    "điều hòa": "aircon",
    "wc": "private_wc",
    "ve_sinh_rieng": "private_wc",
    "wc riêng": "private_wc",
    "vệ sinh riêng": "private_wc",
    "gac": "mezzanine",
    "có gác": "mezzanine",
    "co gac": "mezzanine",
    "gác": "mezzanine",
    "gác lửng": "mezzanine",
    "gác cao": "mezzanine",
    "gác xép": "mezzanine",
    "gác lưng": "mezzanine",
    "gác lững": "mezzanine",
    "gác đúc": "mezzanine",
    "gác gỗ": "mezzanine",
    "mezzanine": "mezzanine",
    "bep": "kitchen",
    "kitchen_shelf": "kitchen",
    "kệ bếp": "kitchen",
    "tu_lanh": "fridge",
    "tủ lạnh": "fridge",
    "may_giat": "washing_machine",
    "máy giặt": "washing_machine",
    "balcony": "window_balcony",
    "window": "window_balcony",
    "ban_cong": "window_balcony",
    "ban công": "window_balcony",
    "cua_so": "window_balcony",
    "cửa sổ": "window_balcony",
    "full_noi_that": "furniture",
    "noi_that": "furniture",
    "nội thất": "furniture",
    "xe": "parking",
    "ham_xe": "parking",
    "chỗ để xe": "parking",
    "pet": "pet_allowed",
    "cho_nuoi_pet": "pet_allowed",
    "thu_cung": "pet_allowed",
    "thú cưng": "pet_allowed",
    "nuôi mèo": "pet_allowed",
    "nuôi chó": "pet_allowed",
    "tu_do": "free_hours",
    "gio_tu_do": "free_hours",
    "free_time": "free_hours",
    "giờ giấc tự do": "free_hours",
    "khong_chung_chu": "no_shared_landlord",
    "private_entrance": "no_shared_landlord",
    "không chung chủ": "no_shared_landlord",
    "van_tay": "fingerprint_lock",
    "the_tu": "fingerprint_lock",
    "khoa_van_tay": "fingerprint_lock",
    "smart_lock": "fingerprint_lock",
    "khoá vân tay": "fingerprint_lock",
    "khóa vân tay": "fingerprint_lock",
    "bao_ve": "guard",
    "security": "guard",
    "bảo vệ": "guard",
}


def _normalize_amenity(code: str) -> str:
    if not code:
        return code
    c = code.strip().lower()
    return _ALIAS_MAP.get(c, c)


_NORMALIZE_AMENITY = _normalize_amenity


def _amenity_fit(
    requested: Optional[Sequence[str]],
    concept_scores: Optional[Mapping[str, float]],
    amenity_overall: Optional[float] = None,
) -> float:
    """Điểm trung bình của các tiện ích user yêu cầu (thiếu dữ liệu -> trung tính).
    Hỗ trợ alias chuẩn hóa về canonical taxonomy (cả tiếng Việt có dấu lẫn mã tiếng Anh).
    Khi không có tiện ích cụ thể nào được yêu cầu, fallback về amenity_overall nếu có.
    """
    scores = concept_scores or {}
    if not requested:
        if amenity_overall is not None:
            return _clamp01(amenity_overall)
        if "amenity_overall" in scores:
            return _clamp01(scores["amenity_overall"])
        return 1.0

    normalized_req = list(dict.fromkeys(_normalize_amenity(str(a)) for a in requested if str(a).strip()))
    if not normalized_req:
        if amenity_overall is not None:
            return _clamp01(amenity_overall)
        if "amenity_overall" in scores:
            return _clamp01(scores["amenity_overall"])
        return 1.0

    return sum(_clamp01(float(scores.get(a, UNKNOWN_SCORE))) for a in normalized_req) / len(normalized_req)


# --- Weights ---
def _dynamic_weights(user_pref: object, base: Mapping[str, float]) -> dict[str, float]:
    """Chỉ giữ tiêu chí user có nói tới, rồi chuẩn hóa L1 để tổng trọng số = 1.0.
    Sử dụng base.get(k) an toàn để không văng KeyError khi AI Agent gửi bộ trọng số rút gọn.
    """
    lat = _get(user_pref, "lat")
    lng = _get(user_pref, "lng")
    amenities = _get(user_pref, "amenities")
    include_overall = bool(_get(user_pref, "include_amenity_overall", False))

    active = {
        "price": True,     # Bắt buộc: luôn đánh giá mức độ hợp lý của giá phòng (price_score từ ML)
        "safety": True,    # Bắt buộc: luôn đánh giá điểm an ninh (safety_score)
        "semantic": True,  # Bắt buộc: luôn đánh giá độ khớp ngữ nghĩa (similarity_score)
        "location": lat is not None and lng is not None,  # Động: chỉ bật khi có toạ độ mục tiêu
        "amenity": bool(amenities) or include_overall,    # Động: bật khi có tiện ích cụ thể hoặc yêu cầu overall
    }
    w = {k: float(base.get(k, DEFAULT_WEIGHTS.get(k, 0.2))) for k, on in active.items() if on}
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
        return _location_fit(_haversine_km(float(lat), float(lng), float(pref_lat), float(pref_lng))) # type: ignore
    except (ValueError, TypeError):
        return UNKNOWN_SCORE


def _price_fit(orm: object) -> float:
    """Điểm hợp lý giá (price_score) do mô hình Machine Learning (Conformal ML / PriceEvaluator) thẩm định.
    - price_score >= 0.75: Giá rất hời / rẻ so với giá trị thực tế của phòng.
    - price_score ≈ 0.50: Giá hợp lý, ngang giá trị thị trường.
    - price_score <= 0.25: Giá đắt hơn so với mặt bằng.
    Nếu tin đăng chưa được mô hình ML chấm điểm (price_score IS NULL), mặc định là mức trung bình thị trường 0.50.
    """
    price_score = _get(orm, "price_score")
    if price_score is not None:
        try:
            return _clamp01(float(price_score)) # type: ignore
        except (ValueError, TypeError):
            pass
    return 0.50


def _match_breakdown(
    listing: object,
    user_pref: object,
    weights: dict[str, float],
) -> dict[str, object]:
    """Tính điểm từng thành phần dựa trên weights đã pre-computed theo mô hình MCDM."""
    orm = _get(listing, "listing", listing)
    scorers = {
        "price": lambda: _price_fit(orm),
        "safety": lambda: _score_or_unknown(orm, "safety_score"),
        "location": lambda: _location_part(listing, user_pref),
        "amenity": lambda: _amenity_fit(
            _get(user_pref, "amenities"), # type: ignore
            _get(orm, "concept_scores"), # type: ignore
            _get(orm, "amenity_overall"), # type: ignore
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


def component_influence(
    listings: Sequence[object],
    prefs: Sequence[object],
    base_weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> dict[str, object]:
    """Chẩn đoán offline: ảnh hưởng thực của mỗi thành phần ~ trọng số x độ lệch chuẩn."""
    if not listings or not prefs:
        return {}
    stds: dict[str, list[float]] = {}
    ws: dict[str, list[float]] = {}
    for pref in prefs:
        computed_weights = _dynamic_weights(pref, base_weights)
        bds = [_match_breakdown(l, pref, computed_weights) for l in listings]
        for k in bds[0]["parts"]: # type: ignore
            parts_dict: dict[str, float] = bds[0]["parts"] # type: ignore
            stds.setdefault(k, []).append(pstdev(b["parts"][k] for b in bds)) # type: ignore
            ws.setdefault(k, []).append(parts_dict[k])
    out = {k: {"weight": mean(ws[k]), "std": mean(stds[k])} for k in stds}
    total = sum(v["weight"] * v["std"] for v in out.values()) or 1.0
    for v in out.values():
        v["influence"] = v["weight"] * v["std"] / total
    return out
