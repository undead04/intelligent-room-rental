"""Hệ thống đo lường Information Retrieval (IR) và Constraint Satisfaction cho Homigo.

Cung cấp các metrics chuẩn khoa học để đánh giá năng lực gợi ý phòng trọ:
- Precision@K (P@3, P@5): Tỷ lệ phòng hoàn toàn thỏa mãn trong top K.
- MRR (Mean Reciprocal Rank): 1 / rank của phòng đầu tiên thỏa mãn trọn vẹn.
- nDCG@K: Normalized Discounted Cumulative Gain theo 4 mức liên quan (0 -> 3).
- CSR (Constraint Satisfaction Rate) & Phân rã tuân thủ từng tiêu chí (Price, Distance, RoomType, Area, Amenity).
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Optional, Sequence

try:
    from utils.geo import haversine_km
except ImportError:
    from math import asin, cos, radians, sin, sqrt

    def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Khoảng cách đường chim bay (km) giữa hai toạ độ."""
        p1, l1, p2, l2 = map(radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
        a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin((l2 - l1) / 2) ** 2
        return 6371.0 * 2 * asin(sqrt(a))

try:
    from domain.enums import Amenity, RoomType, normalize_amenity, normalize_room_type
except ImportError:
    Amenity = None  # type: ignore[assignment,misc]
    RoomType = None  # type: ignore[assignment,misc]

    def normalize_amenity(val: Any) -> Any:
        return val

    def normalize_room_type(val: Any) -> Any:
        return val
from eval.datasets.recommendation_benchmark import GroundTruthExpectation


# Bản đồ từ khóa nhận diện tiện ích trong text/tags
_AMENITY_KEYWORDS_MAP: dict[str, tuple[str, ...]] = {
    "aircon": ("máy lạnh", "điều hòa", "điều hoà", "ac", "aircon"),
    "private_wc": ("wc riêng", "vệ sinh riêng", "toilet riêng", "khép kín", "khep kin"),
    "mezzanine": ("gác lửng", "gác lững", "gác đúc", "gác", "có gác"),
    "kitchen": ("kệ bếp", "bếp", "nấu ăn", "chỗ nấu ăn", "nấu nướng"),
    "washing_machine": ("máy giặt", "may giat"),
    "fridge": ("tủ lạnh", "tu lanh"),
    "window_balcony": ("ban công", "cửa sổ", "balcony", "view thoáng", "thoáng mát"),
    "furniture": ("full nội thất", "nội thất", "đầy đủ đồ", "full đồ"),
    "parking": ("chỗ để xe", "hầm xe", "bãi xe", "nhà xe", "giữ xe"),
    "elevator": ("thang máy", "thang may"),
    "free_hours": ("giờ tự do", "24/24", "giờ giấc tự do", "không giới hạn giờ"),
    "no_shared_landlord": ("không chung chủ", "ko chung chủ", "lối đi riêng", "không chung chu"),
    "pet_allowed": ("thú cưng", "pet", "chó", "mèo", "nuôi thú cưng", "nuôi pet"),
    "safe_area": ("an ninh", "camera", "khóa vân tay", "khoá vân tay", "bảo vệ", "khu an ninh"),
    "fingerprint_lock": ("khóa vân tay", "khoá vân tay", "vân tay", "thẻ từ"),
    "camera": ("camera", "camera an ninh"),
    "guard": ("bảo vệ", "bảo vệ 24/7"),
}


def _extract_room_attrs(room: Any) -> dict[str, Any]:
    """Trích xuất chuẩn hoá các thuộc tính cần thiết từ đối tượng Room (dict hoặc RoomItem)."""
    if hasattr(room, "model_dump"):
        # Pydantic BaseModel (RoomItem)
        data = room.model_dump()
        price_num = getattr(room, "priceNum", None)
        if price_num is None or price_num <= 0:
            price_num = data.get("priceNum") or data.get("price_vnd") or 0.0
        lat = getattr(room, "lat", None)
        lng = getattr(room, "lng", None)
        area_m2 = getattr(room, "area_m2", None)
        room_type = getattr(room, "room_type", None)
        tags = list(getattr(room, "tags", []) or []) + list(getattr(room, "inferred_tags", []) or [])
        concept_scores = dict(getattr(room, "concept_scores", {}) or {})
        title = getattr(room, "title", "") or ""
    elif isinstance(room, dict):
        data = room
        listing = room.get("listing") or {}
        price_num = (
            room.get("priceNum")
            or room.get("price_vnd")
            or listing.get("price_vnd")
            or listing.get("priceNum")
            or 0.0
        )
        lat = room.get("lat") or listing.get("lat")
        lng = room.get("lng") or listing.get("lng")
        area_m2 = room.get("area_m2") or listing.get("area_m2")
        room_type = room.get("room_type") or listing.get("room_type")
        tags = list(room.get("tags") or []) + list(listing.get("tags") or []) + list(room.get("inferred_tags") or [])
        concept_scores = dict(room.get("concept_scores") or listing.get("concept_scores") or {})
        title = room.get("title") or listing.get("title") or ""
    else:
        # Generic object
        price_num = getattr(room, "priceNum", getattr(room, "price_vnd", 0.0))
        lat = getattr(room, "lat", None)
        lng = getattr(room, "lng", None)
        area_m2 = getattr(room, "area_m2", None)
        room_type = getattr(room, "room_type", None)
        tags = list(getattr(room, "tags", []) or [])
        concept_scores = dict(getattr(room, "concept_scores", {}) or {})
        title = getattr(room, "title", "") or ""

    try:
        price_num = float(price_num)
    except (TypeError, ValueError):
        price_num = 0.0

    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None

    try:
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lng = None

    try:
        area_m2 = float(area_m2) if area_m2 is not None else None
    except (TypeError, ValueError):
        area_m2 = None

    # Chuẩn hoá RoomType
    normalized_rt_str: Optional[str] = None
    if room_type is not None:
        if hasattr(room_type, "value"):
            normalized_rt_str = str(room_type.value).upper()
        elif isinstance(room_type, dict):
            code = room_type.get("code") or room_type.get("name")
            normalized_rt_str = str(code).upper() if code else None
        else:
            try:
                norm = normalize_room_type(room_type)
                if norm and hasattr(norm, "value"):
                    normalized_rt_str = str(norm.value).upper()
                else:
                    normalized_rt_str = str(room_type).upper().strip()
            except Exception:
                normalized_rt_str = str(room_type).upper().strip()

    return {
        "price_num": price_num,
        "lat": lat,
        "lng": lng,
        "area_m2": area_m2,
        "room_type_str": normalized_rt_str,
        "tags": [str(t) for t in tags],
        "concept_scores": {str(k).lower(): float(v) for k, v in concept_scores.items()},
        "title": str(title),
    }


def _check_single_amenity(
    amenity_code: str,
    concept_scores: dict[str, float],
    tags: list[str],
    title: str,
    score_threshold: float = 0.70,
) -> bool:
    """Kiểm tra một tiện ích có hiện diện trong phòng hay không qua concept_scores, tags hoặc title."""
    code = amenity_code.lower().strip()

    # 1. Trực tiếp từ concept_scores (suy đoán ML hoặc backend phân loại)
    if concept_scores.get(code, 0.0) >= score_threshold:
        return True

    # Trường hợp safe_area có thể thỏa mãn nếu có camera, fingerprint_lock hoặc guard
    if code == "safe_area":
        if any(concept_scores.get(c, 0.0) >= score_threshold for c in ("safe_area", "camera", "fingerprint_lock", "guard")):
            return True

    # Trường hợp tòa nhà tự quản (giờ tự do + khóa vân tay) đồng nghĩa không chung chủ
    if code == "no_shared_landlord":
        if (
            concept_scores.get("free_hours", 0.0) >= score_threshold
            and concept_scores.get("fingerprint_lock", 0.0) >= score_threshold
        ):
            return True

    # 2. Kiểm tra qua từ khóa trong tags & title
    search_text = (title + " " + " ".join(tags)).lower()
    keywords = _AMENITY_KEYWORDS_MAP.get(code, (code,))
    for kw in keywords:
        if kw in search_text:
            return True

    return False


def evaluate_room_satisfaction(
    room: Any,
    expectation: GroundTruthExpectation,
    budget_tolerance_pct: float = 0.0,
) -> dict[str, Any]:
    """Đánh giá chi tiết mức độ thỏa mãn kỳ vọng của một phòng trọ.

    Args:
        room: Dict hoặc đối tượng RoomItem.
        expectation: Đối tượng GroundTruthExpectation chứa các ràng buộc.
        budget_tolerance_pct: Tỷ lệ nới lỏng ngân sách (ví dụ 0.10 cho 10%).

    Returns:
        dict chứa:
            - price_ok: bool
            - distance_ok: bool
            - room_type_ok: bool
            - area_ok: bool
            - amenities_ok: bool
            - is_fully_satisfied: bool
            - relevance_level: int (0: vi phạm ràng buộc cứng, 1: cơ bản, 2: tốt, 3: hoàn hảo)
            - distance_km: Optional[float]
            - price_vnd: float
            - matched_amenities: list[str]
            - missing_amenities: list[str]
            - amenities_matched_ratio: float
    """
    attrs = _extract_room_attrs(room)
    price_num = attrs["price_num"]
    lat = attrs["lat"]
    lng = attrs["lng"]
    area_m2 = attrs["area_m2"]
    room_type_str = attrs["room_type_str"]
    concept_scores = attrs["concept_scores"]
    tags = attrs["tags"]
    title = attrs["title"]

    # 1. Kiểm tra Giá (Price)
    price_ok = True
    if expectation.max_budget is not None:
        allowed_max = expectation.max_budget * (1.0 + max(0.0, budget_tolerance_pct))
        if price_num <= 0 or price_num > allowed_max:
            price_ok = False
    if expectation.min_budget is not None:
        allowed_min = expectation.min_budget * (1.0 - max(0.0, budget_tolerance_pct))
        if price_num < allowed_min:
            price_ok = False

    # 2. Kiểm tra Khoảng cách (Distance)
    distance_ok = True
    dist_km: Optional[float] = None
    if (
        expectation.target_lat is not None
        and expectation.target_lng is not None
        and expectation.max_distance_km is not None
    ):
        if lat is not None and lng is not None:
            dist_km = haversine_km(expectation.target_lat, expectation.target_lng, lat, lng)
            distance_ok = dist_km <= expectation.max_distance_km
        else:
            # Thiếu tọa độ nên không thể xác nhận nằm trong bán kính cho phép
            distance_ok = False

    # 3. Kiểm tra Loại phòng (Room Type)
    room_type_ok = True
    if room_type_str is not None:
        if expectation.forbidden_room_types and room_type_str in [
            str(rt).upper() for rt in expectation.forbidden_room_types
        ]:
            room_type_ok = False
        if expectation.allowed_room_types and room_type_str not in [
            str(rt).upper() for rt in expectation.allowed_room_types
        ]:
            room_type_ok = False
    else:
        # Không có room_type: nếu có ràng buộc cấm cụ thể hoặc bắt buộc cụ thể thì coi như không thỏa
        if expectation.allowed_room_types:
            room_type_ok = False

    # 4. Kiểm tra Diện tích (Area)
    area_ok = True
    if expectation.min_area_m2 is not None:
        if area_m2 is None or area_m2 < expectation.min_area_m2:
            area_ok = False

    # 5. Kiểm tra Tiện ích (Amenities)
    matched_amenities: list[str] = []
    missing_amenities: list[str] = []
    for amenity in expectation.required_amenities:
        if _check_single_amenity(amenity, concept_scores, tags, title):
            matched_amenities.append(amenity)
        else:
            missing_amenities.append(amenity)

    amenities_ok = len(missing_amenities) == 0
    total_req_amenities = len(expectation.required_amenities)
    amenities_matched_ratio = (
        len(matched_amenities) / total_req_amenities if total_req_amenities > 0 else 1.0
    )

    # 6. Xác định Relevance Level & is_fully_satisfied
    # Ràng buộc cứng: Giá, Khoảng cách, Loại phòng
    hard_constraints_met = price_ok and distance_ok and room_type_ok
    is_fully_satisfied = hard_constraints_met and area_ok and amenities_ok

    if not hard_constraints_met:
        relevance_level = 0
    else:
        if is_fully_satisfied:
            relevance_level = 3
        elif area_ok or amenities_matched_ratio >= 0.5:
            relevance_level = 2
        else:
            relevance_level = 1

    return {
        "price_ok": price_ok,
        "distance_ok": distance_ok,
        "room_type_ok": room_type_ok,
        "area_ok": area_ok,
        "amenities_ok": amenities_ok,
        "is_fully_satisfied": is_fully_satisfied,
        "relevance_level": relevance_level,
        "distance_km": round(dist_km, 2) if dist_km is not None else None,
        "price_vnd": price_num,
        "matched_amenities": matched_amenities,
        "missing_amenities": missing_amenities,
        "amenities_matched_ratio": round(amenities_matched_ratio, 4),
    }


def precision_at_k(
    rooms: Sequence[Any],
    expectation: GroundTruthExpectation,
    k: int = 5,
) -> float:
    """Tính Precision@K: Tỷ lệ phòng hoàn toàn thỏa mãn (is_fully_satisfied) trong top K.

    Chuẩn IR: P@K = (Số phòng đạt trong top K) / K.
    Nếu k <= 0 hoặc danh sách phòng rỗng, trả về 0.0.
    """
    if not rooms or k <= 0:
        return 0.0

    top_k = rooms[:k]
    satisfied_count = sum(
        1
        for room in top_k
        if evaluate_room_satisfaction(room, expectation)["is_fully_satisfied"]
    )
    return float(satisfied_count / k)


def reciprocal_rank(
    rooms: Sequence[Any],
    expectation: GroundTruthExpectation,
) -> float:
    """Tính Reciprocal Rank (RR): 1 / rank của phòng đầu tiên thỏa mãn trọn vẹn.

    Nếu không có phòng nào thỏa mãn trong toàn bộ danh sách, trả về 0.0.
    """
    if not rooms:
        return 0.0

    for rank, room in enumerate(rooms, start=1):
        sat = evaluate_room_satisfaction(room, expectation)
        if sat["is_fully_satisfied"]:
            return float(1.0 / rank)

    return 0.0


def ndcg_at_k(
    rooms: Sequence[Any],
    expectation: GroundTruthExpectation,
    k: int = 5,
) -> float:
    """Tính Normalized Discounted Cumulative Gain (nDCG@K) dựa trên relevance_level (0-3).

    Công thức:
        DCG@K = sum_{i=1}^{min(K, N)} (2^{rel_i} - 1) / log2(i + 1)
        IDCG@K = DCG@K với thứ tự relevance giảm dần lý tưởng
        nDCG@K = DCG@K / IDCG@K (trả về 0.0 nếu IDCG == 0.0)
    """
    if not rooms or k <= 0:
        return 0.0

    relevance_levels = [
        evaluate_room_satisfaction(room, expectation)["relevance_level"]
        for room in rooms
    ]

    # Tính DCG@K
    dcg = 0.0
    for i, rel in enumerate(relevance_levels[:k], start=1):
        dcg += (2.0**rel - 1.0) / math.log2(i + 1.0)

    # Tính IDCG@K dựa trên các mức liên quan tốt nhất có thể
    ideal_levels = sorted(relevance_levels, reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_levels, start=1):
        idcg += (2.0**rel - 1.0) / math.log2(i + 1.0)

    if idcg == 0.0:
        return 0.0

    return float(dcg / idcg)


def constraint_satisfaction_breakdown(
    rooms: Sequence[Any],
    expectation: GroundTruthExpectation,
) -> dict[str, float]:
    """Phân rã tỷ lệ tuân thủ các ràng buộc (Constraint Satisfaction Breakdown) trên danh sách phòng.

    Returns:
        dict gồm:
            - price_compliance_pct: Tỷ lệ tuân thủ giá (0.0 -> 1.0)
            - distance_compliance_pct: Tỷ lệ tuân thủ khoảng cách (0.0 -> 1.0)
            - room_type_compliance_pct: Tỷ lệ tuân thủ loại phòng (0.0 -> 1.0)
            - area_compliance_pct: Tỷ lệ tuân thủ diện tích (0.0 -> 1.0)
            - amenities_compliance_pct: Tỷ lệ tuân thủ tiện ích (0.0 -> 1.0)
            - overall_csr: Tỷ lệ thỏa mãn trọn vẹn tất cả tiêu chí (CSR)
    """
    n = len(rooms)
    if n == 0:
        return {
            "price_compliance_pct": 0.0,
            "distance_compliance_pct": 0.0,
            "room_type_compliance_pct": 0.0,
            "area_compliance_pct": 0.0,
            "amenities_compliance_pct": 0.0,
            "overall_csr": 0.0,
        }

    evals = [evaluate_room_satisfaction(room, expectation) for room in rooms]

    return {
        "price_compliance_pct": round(sum(1 for e in evals if e["price_ok"]) / n, 4),
        "distance_compliance_pct": round(sum(1 for e in evals if e["distance_ok"]) / n, 4),
        "room_type_compliance_pct": round(sum(1 for e in evals if e["room_type_ok"]) / n, 4),
        "area_compliance_pct": round(sum(1 for e in evals if e["area_ok"]) / n, 4),
        "amenities_compliance_pct": round(sum(1 for e in evals if e["amenities_ok"]) / n, 4),
        "overall_csr": round(sum(1 for e in evals if e["is_fully_satisfied"]) / n, 4),
    }


def summarize_queries_ir_metrics(queries_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Tổng hợp các chỉ số IR trên toàn bộ tập benchmark queries.

    Nhận vào danh sách kết quả từng query. Nếu query chứa raw 'rooms' và 'expectation',
    hàm sẽ tự động tính toán các chỉ số thành phần.

    Returns:
        dict thống kê tổng hợp:
            - total_queries: Tổng số câu truy vấn
            - mean_precision_at_3: Giá trị trung bình P@3
            - mean_precision_at_5: Giá trị trung bình P@5
            - mrr: Mean Reciprocal Rank
            - mean_ndcg_at_5: Giá trị trung bình nDCG@5
            - mean_csr: Giá trị trung bình Overall CSR
            - by_group: Thống kê chi tiết theo từng nhóm (G1, G2, ...)
            - compliance_breakdown: Thống kê trung bình mức độ tuân thủ từng tiêu chí
    """
    if not queries_results:
        return {
            "total_queries": 0,
            "mean_precision_at_3": 0.0,
            "mean_precision_at_5": 0.0,
            "mrr": 0.0,
            "mean_ndcg_at_5": 0.0,
            "mean_csr": 0.0,
            "by_group": {},
            "compliance_breakdown": {
                "price_compliance": 0.0,
                "distance_compliance": 0.0,
                "room_type_compliance": 0.0,
                "area_compliance": 0.0,
                "amenities_compliance": 0.0,
            },
        }

    processed: list[dict[str, Any]] = []

    for item in queries_results:
        p3 = item.get("precision_at_3")
        p5 = item.get("precision_at_5")
        rr = item.get("reciprocal_rank") or item.get("rr")
        ndcg5 = item.get("ndcg_at_5")
        csr = item.get("overall_csr") or item.get("csr")
        group = item.get("group") or "DEFAULT"
        breakdown = item.get("breakdown") or {}

        # Nếu chưa có sẵn chỉ số nhưng có rooms và expectation -> tính trực tiếp
        if (p5 is None or rr is None) and "rooms" in item and "expectation" in item:
            rooms = item["rooms"]
            exp = item["expectation"]
            p3 = precision_at_k(rooms, exp, k=3)
            p5 = precision_at_k(rooms, exp, k=5)
            rr = reciprocal_rank(rooms, exp)
            ndcg5 = ndcg_at_k(rooms, exp, k=5)
            breakdown = constraint_satisfaction_breakdown(rooms, exp)
            csr = breakdown.get("overall_csr", 0.0)

        processed.append({
            "group": str(group),
            "p3": float(p3 or 0.0),
            "p5": float(p5 or 0.0),
            "rr": float(rr or 0.0),
            "ndcg5": float(ndcg5 or 0.0),
            "csr": float(csr or 0.0),
            "price_comp": float(breakdown.get("price_compliance_pct", 0.0)),
            "dist_comp": float(breakdown.get("distance_compliance_pct", 0.0)),
            "rt_comp": float(breakdown.get("room_type_compliance_pct", 0.0)),
            "area_comp": float(breakdown.get("area_compliance_pct", 0.0)),
            "amenity_comp": float(breakdown.get("amenities_compliance_pct", 0.0)),
        })

    n = len(processed)

    mean_p3 = statistics.fmean(x["p3"] for x in processed)
    mean_p5 = statistics.fmean(x["p5"] for x in processed)
    mean_rr = statistics.fmean(x["rr"] for x in processed)
    mean_ndcg5 = statistics.fmean(x["ndcg5"] for x in processed)
    mean_csr = statistics.fmean(x["csr"] for x in processed)

    # Thống kê theo group
    by_group: dict[str, dict[str, float]] = {}
    groups = {x["group"] for x in processed}
    for g in sorted(groups):
        g_items = [x for x in processed if x["group"] == g]
        by_group[g] = {
            "count": len(g_items),
            "mean_precision_at_3": round(statistics.fmean(x["p3"] for x in g_items), 4),
            "mean_precision_at_5": round(statistics.fmean(x["p5"] for x in g_items), 4),
            "mrr": round(statistics.fmean(x["rr"] for x in g_items), 4),
            "mean_ndcg_at_5": round(statistics.fmean(x["ndcg5"] for x in g_items), 4),
            "mean_csr": round(statistics.fmean(x["csr"] for x in g_items), 4),
        }

    compliance_breakdown = {
        "price_compliance": round(statistics.fmean(x["price_comp"] for x in processed), 4),
        "distance_compliance": round(statistics.fmean(x["dist_comp"] for x in processed), 4),
        "room_type_compliance": round(statistics.fmean(x["rt_comp"] for x in processed), 4),
        "area_compliance": round(statistics.fmean(x["area_comp"] for x in processed), 4),
        "amenities_compliance": round(statistics.fmean(x["amenity_comp"] for x in processed), 4),
    }

    return {
        "total_queries": n,
        "mean_precision_at_3": round(mean_p3, 4),
        "mean_precision_at_5": round(mean_p5, 4),
        "mrr": round(mean_rr, 4),
        "mean_ndcg_at_5": round(mean_ndcg5, 4),
        "mean_csr": round(mean_csr, 4),
        "by_group": by_group,
        "compliance_breakdown": compliance_breakdown,
    }
