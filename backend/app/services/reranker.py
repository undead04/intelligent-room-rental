"""MCDM Dynamic Reranking Engine cho Smart Housing Search.

Đánh giá và tái xếp hạng danh sách tin phòng từ Hybrid Search theo Multi-Criteria Decision Making (MCDM):
1. Giá (price): Đánh giá mức độ hợp lý thông qua ML PriceEvaluator.
2. Vị trí (location): Haversine distance tới tọa độ mong muốn của người dùng.
3. Tiện nghi (amenity): Tỷ lệ đáp ứng các tiện ích ưu tiên mềm (canonical taxonomy 17 tiện ích).
4. An ninh (safety): Điểm an ninh tổng hợp của khu trọ.
5. Ngữ nghĩa (semantic): Điểm tương đồng ngữ nghĩa từ Dense pgvector Embedding.

Public API:
    rerank(candidates, user_pref, limit, base_weights) -> [(breakdown, listing)]
    explain_match(breakdown, top_n)                   -> dict giải thích cho AI
    DEFAULT_WEIGHTS                                   -> dict trọng số cơ sở 5 tiêu chí
"""
from datetime import datetime, timezone
from math import asin, cos, exp, log, radians, sin, sqrt
from typing import Mapping, Optional, Sequence

__all__ = ["rerank", "explain_match", "DEFAULT_WEIGHTS"]

# --- Constants ---
UNKNOWN_SCORE: float = 0.0
EARTH_RADIUS_KM: float = 6371.0
DEFAULT_NEAR_KM: float = 0.8
DEFAULT_HALF_LIFE_KM: float = 3.0
_LN2: float = log(2.0)
BASELINE_AMENITY_WEIGHT: float = 0.10
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


def _location_fit(
    dist_km: float,
    near_km: float = DEFAULT_NEAR_KM,
    far_km: Optional[float] = 5.0,
    half_life_km: float = DEFAULT_HALF_LIFE_KM,
) -> float:
    """<= near_km -> 1.0; > far_km (nếu có trần) -> 0.0;
    trong bán kính hợp lệ áp dụng suy giảm mũ bán rã: exp(-ln(2) * (dist - near_km) / half_life_km).
    """
    if dist_km <= near_km:
        return 1.0
    if far_km is not None and dist_km > far_km:
        return 0.0
    h = max(0.1, float(half_life_km))
    return _clamp01(exp(-_LN2 * (dist_km - near_km) / h))


def _normalize_amenity(code: object) -> str:
    """Chuẩn hoá mã tiện ích từ Enum hoặc chuỗi về canonical code chữ thường."""
    if not code:
        return ""
    val = getattr(code, "value", code)
    return str(val).strip().lower()


def _amenity_fit(
    concept_scores: Optional[Mapping[str, float]] = None,
    amenity_overall: Optional[float] = None,
    preferred: Optional[Sequence[object]] = None,
    missing_overall_default: float = 1.0,
) -> float:
    """Điểm tiện ích trong MCDM Rerank (Phương án 3 - Kết hợp):
    - Tiện ích bắt buộc (requested) đã được lọc cứng (Pass/Fail) ở SQL & Grounding,
      tuyệt đối KHÔNG chấm điểm lặp lại trong MCDM.
    - Nếu có tiện ích ưu tiên mềm (preferred): tính độ thỏa mãn của preferred (70%) + tiện ích tổng thể (30%).
    - Nếu không có preferred: chấm theo amenity_overall (hoặc missing_overall_default nếu thiếu dữ liệu).
    """
    scores = concept_scores or {}
    overall_val = (
        _clamp01(amenity_overall)
        if amenity_overall is not None
        else (_clamp01(scores["amenity_overall"]) if "amenity_overall" in scores else missing_overall_default)
    )

    if preferred:
        norm_pref = list(dict.fromkeys(_normalize_amenity(a) for a in preferred if _normalize_amenity(a)))
        if norm_pref:
            pref_fit = sum(_clamp01(float(scores.get(a, UNKNOWN_SCORE))) for a in norm_pref) / len(norm_pref)
            return _clamp01(0.7 * pref_fit + 0.3 * overall_val)

    return overall_val


_SAFETY_AMENITIES = frozenset({"safe_area", "camera", "guard", "fingerprint_lock"})


def _has_caller_amenity_weight(base: Optional[Mapping[str, float]]) -> bool:
    """True khi caller chủ động truyền vector base_weights tùy chỉnh có amenity > 0."""
    return (
        base is not None
        and base is not DEFAULT_WEIGHTS
        and "amenity" in base
        and float(base.get("amenity", 0.0)) > 0
    )


def _has_caller_safety_weight(base: Optional[Mapping[str, float]]) -> bool:
    """True khi caller chủ động truyền vector base_weights tùy chỉnh có safety > 0."""
    return (
        base is not None
        and base is not DEFAULT_WEIGHTS
        and "safety" in base
        and float(base.get("safety", 0.0)) > 0
    )


def _has_explicit_safety_intent(user_pref: object, base: Optional[Mapping[str, float]]) -> bool:
    """Chỉ bật trụ cột an ninh (safety) khi người dùng nhắc tới an ninh/an toàn hoặc caller yêu cầu."""
    if _has_caller_safety_weight(base) or bool(_get(user_pref, "include_safety", False)):
        return True
    for field in ("amenities", "preferred_amenities"):
        items = _get(user_pref, field)
        if not items or isinstance(items, (str, bytes)):
            continue
        for item in items: # type: ignore
            if _normalize_amenity(item) in _SAFETY_AMENITIES:
                return True
    return False


def _has_explicit_amenity_intent(user_pref: object, base: Optional[Mapping[str, float]]) -> bool:
    """Xác định người dùng có chủ động yêu cầu ưu tiên tiện nghi mềm hay không.

    Không suy diễn từ `base['amenity'] > 0` vì AI Agent luôn truyền đủ trọng số
    (kể cả khi nói chung chung với mức nền nhẹ).
    """
    preferred_amenities = _get(user_pref, "preferred_amenities")
    include_overall = bool(_get(user_pref, "include_amenity_overall", False))
    return bool(preferred_amenities) or include_overall


# --- Weights ---
def _dynamic_weights(user_pref: object, base: Optional[Mapping[str, float]] = None) -> dict[str, float]:
    """Chỉ giữ tiêu chí đang bật, rồi chuẩn hóa L1 để tổng trọng số = 1.0.
    - Tiện ích bắt buộc (amenities) chỉ lọc cứng ở SQL & Grounding, KHÔNG kích hoạt trọng số đầy đủ.
    - Trọng số amenity bật ở mức đầy đủ khi có preferred_amenities, include_amenity_overall,
      hoặc caller chủ động truyền trọng số 'amenity' > 0 trong base_weights tùy chỉnh.
    - Trụ cột safety chỉ bật khi người dùng nhắc tới an ninh/an toàn (tiện ích an ninh,
      include_safety=True, hoặc caller chủ động truyền safety > 0 trong weights tùy chỉnh).
    """
    eff_base = base if base is not None else DEFAULT_WEIGHTS
    lat = _get(user_pref, "lat")
    lng = _get(user_pref, "lng")
    has_explicit_amenity = _has_explicit_amenity_intent(user_pref, base)
    use_caller_amenity_weight = _has_caller_amenity_weight(base)
    caller_disabled_amenity = (
        base is not None
        and base is not DEFAULT_WEIGHTS
        and "amenity" in base
        and float(base.get("amenity", 0.0)) <= 0.0
    )

    active = {
        "price": True,     # Bắt buộc: luôn đánh giá mức độ hợp lý của giá phòng (price_score từ ML)
        "safety": _has_explicit_safety_intent(user_pref, base),  # Động: chỉ bật khi người dùng nhắc an ninh/an toàn
        "semantic": True,  # Bắt buộc: luôn đánh giá độ khớp ngữ nghĩa (similarity_score)
        "location": lat is not None and lng is not None,  # Động: chỉ bật khi có toạ độ mục tiêu
        "amenity": not caller_disabled_amenity,
    }
    w: dict[str, float] = {}
    for k, on in active.items():
        if not on:
            continue
        if k == "amenity" and not has_explicit_amenity and not use_caller_amenity_weight:
            w[k] = BASELINE_AMENITY_WEIGHT
        else:
            w[k] = float(eff_base.get(k, DEFAULT_WEIGHTS.get(k, 0.2)))
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
        far_km = float(max_dist) if max_dist else None
        return _location_fit(dist, near_km=DEFAULT_NEAR_KM, far_km=far_km, half_life_km=DEFAULT_HALF_LIFE_KM)
    except (ValueError, TypeError):
        return UNKNOWN_SCORE


def _price_fit(orm: object, user_pref: object = None, weights: Optional[Mapping[str, float]] = None) -> float:
    """Điểm hợp lý giá (price_score) do mô hình Machine Learning thẩm định kết hợp mức phù hợp ngân sách."""
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
            # Chỉ bật chế độ ưu tiên giá rẻ danh nghĩa khi người dùng/caller yêu cầu tường minh,
            # không suy diễn từ trọng số sau L1-normalization (tránh tự bật khi location/amenity tắt).
            prefer_cheap = bool(_get(user_pref, "prefer_cheapest")) if user_pref else False

            if prefer_cheap:
                savings_ratio = max(0.0, min(1.0, (m_val - p_val) / m_val))
                # Đẩy tỷ trọng độ rẻ tiền thực tế (savings_ratio) lên 85%, ML score chỉ 15%
                return _clamp01(0.85 * (0.3 + 0.7 * savings_ratio) + 0.15 * ml_score)

            # Mặc định: giữ điểm tối đa cho dải ngân sách kỳ vọng [0.65 * max_price .. max_price],
            # tránh thiên vị phòng giá quá thấp (vd 4-5tr) khi khách tìm phân khúc max 10tr.
            util_ratio = max(0.0, min(1.0, p_val / m_val))
            if util_ratio >= 0.65:
                budget_band_fit = 1.0
            else:
                budget_band_fit = 0.20 + 0.80 * (util_ratio / 0.65)
            return _clamp01(0.45 * ml_score + 0.55 * budget_band_fit)
        else:
            return _clamp01(0.3 * ml_score)

    return ml_score


def _parse_posted_datetime(raw: object) -> Optional[datetime]:
    """Chuẩn hóa posted_date (datetime naive/aware hoặc chuỗi ISO) về UTC."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _freshness_factor(orm: object, now_utc: Optional[datetime] = None) -> float:
    """Hệ số ưu tiên tin mới đăng trong [0.92 .. 1.00]:
    - <= 7 ngày: 1.00
    - 7..30 ngày: giảm tuyến tính 1.00 -> 0.96
    - 30..90 ngày: giảm tuyến tính 0.96 -> 0.92
    - > 90 ngày: 0.92 | Thiếu ngày đăng: 0.97 (trung tính nhẹ).
    """
    posted = _parse_posted_datetime(_get(orm, "posted_date"))
    if posted is None:
        return 0.97
    ref = now_utc or datetime.now(timezone.utc)
    age_days = max(0.0, (ref - posted).total_seconds() / 86400.0)
    if age_days <= 7.0:
        return 1.0
    if age_days <= 30.0:
        return 1.0 - 0.04 * ((age_days - 7.0) / 23.0)
    if age_days <= 90.0:
        return 0.96 - 0.04 * ((age_days - 30.0) / 60.0)
    return 0.92


def _completeness_factor(orm: object) -> float:
    """Phạt nhẹ tin đăng thiếu thông tin cốt lõi trong [0.92 .. 1.00]:
    - Thiếu ảnh thật (images & main_image): -0.03
    - Thiếu diện tích hợp lệ (area_m2 <= 0 hoặc None): -0.03
    - Thiếu giá niêm yết (price_vnd <= 0 hoặc None): -0.02
    """
    penalty = 0.0
    images = _get(orm, "images")
    main_image = _get(orm, "main_image")
    has_images_list = isinstance(images, (list, tuple)) and len(images) > 0
    has_main_image = isinstance(main_image, str) and bool(main_image.strip()) and "placeholder" not in main_image.lower()
    if not (has_images_list or has_main_image):
        penalty += 0.03

    area = _get(orm, "area_m2")
    has_area = False
    if area is not None:
        try:
            has_area = float(area) > 0
        except (ValueError, TypeError):
            has_area = False
    if not has_area:
        penalty += 0.03

    price = _get(orm, "price_vnd")
    has_price = False
    if price is not None:
        try:
            has_price = float(price) > 0
        except (ValueError, TypeError):
            has_price = False
    if not has_price:
        penalty += 0.02

    return max(0.92, 1.0 - penalty)


def _match_breakdown(
    listing: object,
    user_pref: object,
    weights: dict[str, float],
    missing_amenity_default: float = 1.0,
    now_utc: Optional[datetime] = None,
) -> dict[str, object]:
    """Tính điểm từng thành phần dựa trên weights đã pre-computed theo mô hình MCDM,
    sau đó nhân nhẹ hệ số độ mới (`posted_date`) & độ đầy đủ thông tin tin đăng.
    """
    orm = _get(listing, "listing", listing)
    scorers = {
        "price": lambda: _price_fit(orm, user_pref, weights=weights),
        "safety": lambda: _score_or_unknown(orm, "safety_score"),
        "location": lambda: _location_part(listing, user_pref),
        "amenity": lambda: _amenity_fit(
            _get(orm, "concept_scores"), # type: ignore
            _get(orm, "amenity_overall"), # type: ignore
            preferred=_get(user_pref, "preferred_amenities"), # type: ignore
            missing_overall_default=missing_amenity_default,
        ),
        "semantic": lambda: _score_or_unknown(listing, "similarity_score") if isinstance(listing, Mapping) and "similarity_score" in listing else _score_or_unknown(orm, "similarity_score"),
    }
    parts: dict[str, float] = {k: scorers[k]() for k in weights}
    contributions: dict[str, float] = {k: weights[k] * parts[k] for k in parts}
    base_score = sum(contributions.values())
    freshness = _freshness_factor(orm, now_utc=now_utc)
    completeness = _completeness_factor(orm)
    quality_factor = round(freshness * completeness, 4)
    return {
        "score": base_score * quality_factor,
        "base_score": base_score,
        "quality_factor": quality_factor,
        "freshness_factor": round(freshness, 4),
        "completeness_factor": round(completeness, 4),
        "parts": parts,
        "weights": weights,
        "contributions": contributions,
    }


# --- Public API ---
def rerank(
    candidates: list[object],
    user_pref: object,
    limit: int = 5,
    base_weights: Optional[Mapping[str, float]] = None,
) -> list[tuple[dict[str, object], object]]:
    """Xếp hạng candidates (từ vector search). Trả về [(breakdown, listing)] đã sort giảm dần."""
    if not candidates:
        return []

    effective_weights = base_weights or DEFAULT_WEIGHTS
    computed_weights = _dynamic_weights(user_pref, effective_weights)
    # Tin thiếu hoàn toàn amenity_overall/concept_scores luôn nhận UNKNOWN_SCORE (0.0) khi rerank
    missing_amenity_default = UNKNOWN_SCORE
    batch_now = datetime.now(timezone.utc)

    scored = [
        (
            _match_breakdown(
                c,
                user_pref,
                computed_weights,
                missing_amenity_default=missing_amenity_default,
                now_utc=batch_now,
            ),
            c,
        )
        for c in candidates
    ]
    scored.sort(
        key=lambda x: (
            round(float(x[0]["score"]), 8), # type: ignore
            str(_get(_get(x[1], "listing", x[1]), "id", "")),
        ),
        reverse=True,
    )
    return scored[:limit]


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
