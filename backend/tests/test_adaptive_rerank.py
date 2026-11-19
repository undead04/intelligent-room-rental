"""Bộ kiểm thử Black-box độc lập cho MCDM Dynamic Reranking Engine (MỐC 1).

Bao gồm đủ 4 nhóm kiểm thử:
1. Happy path (Ca kiểm thử G2_05: Ưu tiên vị trí gần hơn tiện nghi xa).
2. Trọng số & Chuẩn hóa L1 (Bộ trọng số mới: location=0.25, price=0.25, safety=0.20, amenity=0.20, semantic=0.10).
3. Boundary & Edge cases (Khoảng cách tại near_km, far_km, vượt far_km, không có tọa độ).
4. Corner & Negative cases (Danh sách rỗng, cắt limit, lỗi tọa độ phi số).
"""
import pytest
from app.services.reranker import (
    DEFAULT_WEIGHTS,
    UNKNOWN_SCORE,
    _dynamic_weights,
    _haversine_km,
    _location_fit,
    _location_part,
    explain_match,
    rerank,
)


# ============================================================================
# 1. HAPPY PATH & CA G2_05 VERIFICATION
# ============================================================================

def test_case_g2_05_location_overrides_distant_amenity():
    """Happy Path & Case G2_05:
    Tìm phòng quanh ĐH Bách Khoa CS1 (Quận 10) với bán kính tìm kiếm 3.0km (max_distance_km=3.0).
    - Phòng A: Đường 3 Tháng 2, Quận 10 (cách Bách Khoa ~910m / 0.91km), giá 4.2tr, 1 tiện ích (máy lạnh).
    - Phòng B: Tân Phú (cách Bách Khoa ~4.4km), giá 3.8tr, full tiện ích (máy lạnh, gác lửng, WC riêng, bếp).
    Kiểm chứng:
    + Phòng A đạt điểm location_fit cao vượt trội (>= 0.95).
    + Phòng B bị điểm location_fit = 0.0 (do vượt quá far_km=3.0).
    + Khi rerank, phòng A cách 910m bắt buộc phải xếp trên phòng B cách 4.4km!
    + explain_match xác nhận location là yếu tố hàng đầu của Phòng A.
    """
    # Tọa độ ĐH Bách Khoa CS1: 10.7721° N, 106.6579° E
    bach_khoa_lat = 10.7721
    bach_khoa_lng = 106.6579

    # Phòng A: Đường 3 Tháng 2, Q10 (cách ~0.91km)
    # 0.91km tương đương độ lệch vĩ độ ~0.008184°
    room_a_lat = bach_khoa_lat + 0.008184
    room_a_lng = bach_khoa_lng
    dist_a = _haversine_km(bach_khoa_lat, bach_khoa_lng, room_a_lat, room_a_lng)
    assert 0.90 <= dist_a <= 0.92, f"Khoảng cách phòng A phải ~0.91km, thực tế: {dist_a}"

    # Phòng B: Tân Phú (cách ~4.40km)
    # 4.40km tương đương độ lệch vĩ độ ~0.03957°
    room_b_lat = bach_khoa_lat + 0.03957
    room_b_lng = bach_khoa_lng
    dist_b = _haversine_km(bach_khoa_lat, bach_khoa_lng, room_b_lat, room_b_lng)
    assert 4.39 <= dist_b <= 4.41, f"Khoảng cách phòng B phải ~4.4km, thực tế: {dist_b}"

    # Ứng viên Phòng A: 4.2 triệu, ít tiện ích hơn
    candidate_a = {
        "id": "room_a_q10",
        "listing": {
            "id": "room_a_q10",
            "title": "Phòng trọ Ba Tháng Hai Quận 10 cách Bách Khoa 910m",
            "lat": room_a_lat,
            "lng": room_a_lng,
            "price_vnd": 4_200_000,
            "price_score": 0.85,
            "safety_score": 0.85,
            "concept_scores": {"aircon": 1.0, "amenity_overall": 0.60},
            "similarity_score": 0.80,
        },
    }

    # Ứng viên Phòng B: 3.8 triệu, full tiện ích cao cấp
    candidate_b = {
        "id": "room_b_tan_phu",
        "listing": {
            "id": "room_b_tan_phu",
            "title": "Phòng trọ Tân Phú full tiện ích",
            "lat": room_b_lat,
            "lng": room_b_lng,
            "price_vnd": 3_800_000,
            "price_score": 0.95,
            "safety_score": 0.90,
            "concept_scores": {
                "aircon": 1.0,
                "mezzanine": 1.0,
                "private_wc": 1.0,
                "kitchen": 1.0,
                "amenity_overall": 1.0,
            },
            "similarity_score": 0.90,
        },
    }

    user_pref = {
        "lat": bach_khoa_lat,
        "lng": bach_khoa_lng,
        "max_distance_km": 3.0,
        "max_price": 5_000_000,
        "preferred_amenities": ["aircon", "mezzanine", "private_wc"],
    }

    # 1. Kiểm chứng điểm location_fit đơn lẻ
    fit_a = _location_fit(dist_a, near_km=0.8, far_km=3.0)
    fit_b = _location_fit(dist_b, near_km=0.8, far_km=3.0)
    assert fit_a >= 0.95, f"Phòng A cách 910m phải có location_fit >= 0.95, thực tế: {fit_a}"
    assert fit_b == 0.0, f"Phòng B cách 4.4km (vượt max 3.0km) phải có location_fit = 0.0, thực tế: {fit_b}"

    # 2. Kiểm chứng _location_part
    loc_part_a = _location_part(candidate_a, user_pref)
    loc_part_b = _location_part(candidate_b, user_pref)
    assert loc_part_a >= 0.95
    assert loc_part_b == 0.0

    # 3. Chạy rerank
    results = rerank([candidate_a, candidate_b], user_pref=user_pref, limit=5)
    assert len(results) == 2

    top_breakdown, top_listing = results[0]
    second_breakdown, second_listing = results[1]

    # BẮT BUỘC: Phòng A (cách 910m) xếp trên Phòng B (cách 4.4km)
    assert top_listing["id"] == "room_a_q10", (
        f"Phòng A gần điểm mốc (910m) phải xếp hạng 1, nhưng hạng 1 là: {top_listing['id']}"
    )
    assert second_listing["id"] == "room_b_tan_phu"
    assert top_breakdown["score"] > second_breakdown["score"]

    # 4. Kiểm tra explain_match
    exp_a = explain_match(top_breakdown)
    top_factors_a = [f["name"] for f in exp_a["top_factors"]]
    assert "location" in top_factors_a[:2], "Location phải nằm trong top 2 nhân tố đóng góp điểm cho Phòng A"

    exp_b = explain_match(second_breakdown)
    parts_b = second_breakdown["parts"]
    assert parts_b["location"] == 0.0
    assert second_breakdown["contributions"]["location"] == 0.0


# ============================================================================
# 2. TRỌNG SỐ MỚI & CHUẨN HÓA L1 (WEIGHTS & NORMALIZATION)
# ============================================================================

def test_default_weights_specification():
    """Kiểm tra cấu hình bộ trọng số chuẩn 5 tiêu chí mới:
    - location: 0.25 (tăng từ 0.20)
    - price: 0.25 (giữ vững)
    - safety: 0.20 (giữ vững)
    - amenity: 0.20 (giữ vững)
    - semantic: 0.10 (giảm từ 0.15)
    Tổng trọng số L1 = 1.0.
    """
    assert DEFAULT_WEIGHTS["location"] == 0.25
    assert DEFAULT_WEIGHTS["price"] == 0.25
    assert DEFAULT_WEIGHTS["safety"] == 0.20
    assert DEFAULT_WEIGHTS["amenity"] == 0.20
    assert DEFAULT_WEIGHTS["semantic"] == 0.10
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_l1_normalization_when_location_and_safety_inactive():
    """Khi không có tọa độ người dùng và không nhắc an ninh, location & safety tắt:
    Chuẩn hóa L1 phải phân bổ lại trọng số và semantic luôn là tiêu chí có trọng số thấp nhất.
    Khi có tiện ích an ninh ('safe_area'), safety tự động bật lại.
    """
    # Kịch bản A: Không có location, không nhắc safety, có preferred_amenities (bật: price, amenity, semantic)
    pref_with_amenity = {"preferred_amenities": ["aircon"]}
    w_a = _dynamic_weights(pref_with_amenity, DEFAULT_WEIGHTS)

    assert "location" not in w_a
    assert "safety" not in w_a
    assert set(w_a.keys()) == {"price", "amenity", "semantic"}
    assert sum(w_a.values()) == pytest.approx(1.0)

    # Tổng cơ sở bật = 0.25 + 0.20 + 0.10 = 0.55
    assert w_a["price"] == pytest.approx(0.25 / 0.55)
    assert w_a["amenity"] == pytest.approx(0.20 / 0.55)
    assert w_a["semantic"] == pytest.approx(0.10 / 0.55)
    # Semantic phải là thấp nhất
    assert w_a["semantic"] < w_a["price"]
    assert w_a["semantic"] < w_a["amenity"]
    assert min(w_a, key=w_a.get) == "semantic"

    # Kịch bản B: Không có location, không nhắc an ninh, không có amenity ưu tiên (bật: price, semantic + amenity nền nhẹ)
    pref_minimal = {}
    w_b = _dynamic_weights(pref_minimal, DEFAULT_WEIGHTS)

    assert set(w_b.keys()) == {"price", "amenity", "semantic"}
    assert sum(w_b.values()) == pytest.approx(1.0)

    # Tổng cơ sở bật = 0.25 + 0.10 (amenity nền) + 0.10 = 0.45
    assert w_b["price"] == pytest.approx(0.25 / 0.45)
    assert w_b["amenity"] == pytest.approx(0.10 / 0.45)
    assert w_b["semantic"] == pytest.approx(0.10 / 0.45)
    assert w_b["amenity"] < w_b["price"]

    # Kịch bản C: Có nhắc an ninh (camera/safe_area) -> safety bật cùng (price, amenity, semantic)
    w_c = _dynamic_weights({"preferred_amenities": ["aircon", "safe_area"]}, DEFAULT_WEIGHTS)
    assert set(w_c.keys()) == {"price", "safety", "amenity", "semantic"}
    assert w_c["safety"] == pytest.approx(0.20 / 0.75)


# ============================================================================
# 3. BOUNDARY & EDGE CASES (NGƯỠNG KHOẢNG CÁCH & TỌA ĐỘ)
# ============================================================================

def test_location_fit_boundary_conditions():
    """Kiểm tra chặt chẽ các điểm giới hạn của hàm suy giảm mũ bán rã (Exponential Half-life) _location_fit:
    1. dist <= near_km (0.0, 0.5, 0.8 km) -> 1.0
    2. dist == far_km (2.5, 3.0, 5.0 km) -> giữ điểm dương theo bán rã (không tụt về 0.0 tại biên hợp lệ)
    3. dist > far_km (3.001km, 5.001km, 10.0km) -> 0.0 (vượt bán kính cho phép)
    4. Tại dist = near_km + half_life_km (3.8km với H=3.0): đúng 0.50; bất biến theo far_km khi cùng H.
    5. Tăng trọng số location trong MCDM tự động đẩy phòng sát điểm mốc vượt phòng 2km mà không cần cờ phụ.
    """
    from math import exp, log

    # 1. Bán kính 3.0km (tại biên 3.0km vẫn > 0.5, chỉ về 0.0 khi > 3.0km)
    assert _location_fit(0.0, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(0.5, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(0.8, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(3.0, near_km=0.8, far_km=3.0) == pytest.approx(exp(-log(2.0) * 2.2 / 3.0))
    assert _location_fit(3.001, near_km=0.8, far_km=3.0) == 0.0
    assert _location_fit(10.0, near_km=0.8, far_km=3.0) == 0.0

    # 2. Bất biến theo bán kính lọc: tại 2.0km, far_km=2.5 hay far_km=5.0 đều cho cùng điểm ~0.758
    score_2km_tight = _location_fit(2.0, near_km=0.8, far_km=2.5)
    score_2km_wide = _location_fit(2.0, near_km=0.8, far_km=5.0)
    assert score_2km_tight == pytest.approx(score_2km_wide)
    assert score_2km_wide > 0.70

    # 3. Tại near_km + half_life_km (0.8 + 3.0 = 3.8km) -> đúng 0.50; > 5.0km -> 0.0
    assert _location_fit(3.8, near_km=0.8, far_km=5.0, half_life_km=3.0) == pytest.approx(0.5)
    assert _location_fit(5.0, near_km=0.8, far_km=5.0) > 0.35
    assert _location_fit(5.001, near_km=0.8, far_km=5.0) == 0.0

    # 4. Khi tăng weights["location"] (user nhấn mạnh gần), phòng 0.5km thắng phòng 2.0km tốt hơn chút về giá
    base_lat, base_lng = 10.7721, 106.6579
    near_room = {
        "id": "near_0_5",
        "listing": {
            "id": "near_0_5",
            "lat": base_lat + (0.5 / 110.574),
            "lng": base_lng,
            "price_score": 0.78,
            "safety_score": 0.78,
            "amenity_overall": 0.78,
            "similarity_score": 0.78,
        },
    }
    mid_room = {
        "id": "mid_2_0",
        "listing": {
            "id": "mid_2_0",
            "lat": base_lat + (2.0 / 110.574),
            "lng": base_lng,
            "price_score": 0.85,
            "safety_score": 0.85,
            "amenity_overall": 0.85,
            "similarity_score": 0.85,
        },
    }
    res_boosted = rerank(
        [mid_room, near_room],
        user_pref={"lat": base_lat, "lng": base_lng, "max_distance_km": 2.5},
        base_weights={"location": 0.50, "price": 0.20, "safety": 0.15, "amenity": 0.07, "semantic": 0.08},
        limit=2,
    )
    assert res_boosted[0][1]["id"] == "near_0_5"


def test_location_part_missing_coordinates_safely_disabled():
    """Edge cases: Khi thiếu hoặc sai lệch tọa độ, _location_part phải trả về UNKNOWN_SCORE (0.0)
    an toàn mà không phát sinh ngoại lệ runtime.
    """
    valid_pref = {"lat": 10.7721, "lng": 106.6579}
    valid_listing = {"listing": {"lat": 10.7800, "lng": 106.6580}}

    # Listing thiếu lat hoặc lng
    assert _location_part({"listing": {"lat": None, "lng": 106.6580}}, valid_pref) == UNKNOWN_SCORE
    assert _location_part({"listing": {"lat": 10.7800, "lng": None}}, valid_pref) == UNKNOWN_SCORE
    assert _location_part({"listing": {}}, valid_pref) == UNKNOWN_SCORE

    # User pref thiếu lat hoặc lng
    assert _location_part(valid_listing, {"lat": None, "lng": 106.6579}) == UNKNOWN_SCORE
    assert _location_part(valid_listing, {"lat": 10.7721, "lng": None}) == UNKNOWN_SCORE
    assert _location_part(valid_listing, {}) == UNKNOWN_SCORE

    # Tọa độ không hợp lệ (chuỗi không parse được sang float)
    bad_coords_listing = {"listing": {"lat": "khong_ro", "lng": "chua_co"}}
    assert _location_part(bad_coords_listing, valid_pref) == UNKNOWN_SCORE

    bad_pref = {"lat": "invalid_lat", "lng": "invalid_lng"}
    assert _location_part(valid_listing, bad_pref) == UNKNOWN_SCORE


# ============================================================================
# 4. CORNER & NEGATIVE CASES
# ============================================================================

def test_rerank_empty_and_pagination_corner_cases():
    """Corner cases:
    - candidates rỗng -> trả về []
    - limit <= 0 -> trả về []
    - limit nhỏ hơn tổng số candidate -> cắt đúng limit
    - Hai phòng cùng điểm số -> tie-break ổn định theo id.
    """
    pref = {"lat": 10.7721, "lng": 106.6579}

    # 1. Danh sách rỗng
    assert rerank([], pref) == []

    # 2. Cắt limit & tie-break
    cands = [
        {
            "id": f"room_{i}",
            "listing": {
                "id": f"room_{i}",
                "price_score": 0.8,
                "safety_score": 0.8,
                "lat": 10.7721,
                "lng": 106.6579,
            },
        }
        for i in range(5)
    ]

    top_2 = rerank(cands, pref, limit=2)
    assert len(top_2) == 2
    assert rerank(cands, pref, limit=0) == []
    top_all = rerank(cands, pref, limit=10)
    assert len(top_all) == 5


def test_zero_weights_raises_value_error():
    """Negative case: Nếu caller truyền vào base_weights với tất cả trọng số = 0,
    hệ thống phải raise ValueError("Tổng trọng số của các tiêu chí đang bật phải > 0").
    """
    zero_weights = {"price": 0.0, "safety": 0.0, "semantic": 0.0, "location": 0.0, "amenity": 0.0}
    with pytest.raises(ValueError, match="Tổng trọng số của các tiêu chí đang bật phải > 0"):
        _dynamic_weights({"lat": 10.77, "lng": 106.65}, base=zero_weights)


def test_vague_query_does_not_over_reward_cheap_low_quality_rooms():
    """Khi người dùng nói chung chung (chỉ có max_price, không tọa độ, không preferred_amenities,
    không prefer_cheapest):
    - Trọng số price sau chuẩn hóa L1 (> 0.28) KHÔNG được tự kích hoạt chế độ 'prefer_cheap'.
    - Phòng chất lượng ổn & giá hời theo ML (3.5tr) phải xếp trên phòng siêu rẻ kém tiện nghi (1.6tr).
    - Phòng thiếu dữ liệu tiện nghi (amenity_overall=None) không được thưởng điểm ảo 1.0.
    """
    cheap_low_quality = {
        "id": "cheap_poor",
        "listing": {
            "id": "cheap_poor",
            "price_vnd": 1_600_000,
            "price_score": 0.40,
            "safety_score": 0.40,
            "amenity_overall": 0.15,
            "concept_scores": {},
            "similarity_score": 0.70,
        },
    }
    good_value_room = {
        "id": "good_value",
        "listing": {
            "id": "good_value",
            "price_vnd": 3_500_000,
            "price_score": 0.88,
            "safety_score": 0.75,
            "amenity_overall": 0.85,
            "concept_scores": {"amenity_overall": 0.85},
            "similarity_score": 0.75,
        },
    }
    missing_amenity_room = {
        "id": "missing_meta",
        "listing": {
            "id": "missing_meta",
            "price_vnd": 2_000_000,
            "price_score": 0.60,
            "safety_score": 0.50,
            "amenity_overall": None,
            "concept_scores": {},
            "similarity_score": 0.70,
        },
    }

    vague_pref = {"max_price": 4_000_000}
    results = rerank([cheap_low_quality, missing_amenity_room, good_value_room], user_pref=vague_pref, limit=5)
    assert results[0][1]["id"] == "good_value"
    # Phòng thiếu dữ liệu amenity_overall bị gán UNKNOWN_SCORE (0.0) ở chế độ nền
    missing_bd = next(bd for bd, item in results if item["id"] == "missing_meta")
    assert missing_bd["parts"]["amenity"] == UNKNOWN_SCORE

    # Khi bật tường minh prefer_cheapest=True, phòng rẻ 1.6tr được ưu tiên theo savings_ratio
    cheapest_pref = {"max_price": 4_000_000, "prefer_cheapest": True}
    cheap_bd = rerank([cheap_low_quality, good_value_room], user_pref=cheapest_pref, limit=5)
    bd_map = {item["id"]: bd for bd, item in cheap_bd}
    assert bd_map["cheap_poor"]["parts"]["price"] > bd_map["good_value"]["parts"]["price"]


def test_ai_agent_weights_do_not_reward_missing_amenity_data():
    """Hồi quy Lệch pha #1: Khi AI Agent truyền weights (có amenity > 0), phòng thiếu dữ liệu
    tiện nghi (amenity_overall=None, concept_scores={}) KHÔNG được thưởng điểm 1.0 mà phải nhận
    UNKNOWN_SCORE (0.0) ở cả chế độ nói chung chung lẫn chế độ có preferred_amenities/include_amenity_overall.
    """
    good_room = {
        "id": "good_room",
        "listing": {
            "id": "good_room",
            "price_vnd": 3_400_000,
            "price_score": 0.85,
            "safety_score": 0.75,
            "amenity_overall": 0.85,
            "concept_scores": {"aircon": 1.0, "amenity_overall": 0.85},
            "similarity_score": 0.75,
        },
    }
    missing_amenity_room = {
        "id": "missing_amenity_room",
        "listing": {
            "id": "missing_amenity_room",
            "price_vnd": 3_400_000,
            "price_score": 0.85,
            "safety_score": 0.75,
            "amenity_overall": None,
            "concept_scores": {},
            "similarity_score": 0.75,
        },
    }

    # Kịch bản 1: User nói chung chung, AI Agent gửi vector weights đã chuẩn hóa (amenity=0.15 > 0)
    agent_vague_weights = {"price": 0.39, "safety": 0.31, "semantic": 0.15, "amenity": 0.15}
    res_vague = rerank(
        [missing_amenity_room, good_room],
        user_pref={"max_price": 4_000_000, "include_amenity_overall": False},
        base_weights=agent_vague_weights,
        limit=5,
    )
    assert res_vague[0][1]["id"] == "good_room"
    bd_vague = {item["id"]: bd for bd, item in res_vague}
    assert bd_vague["missing_amenity_room"]["parts"]["amenity"] == UNKNOWN_SCORE
    assert bd_vague["missing_amenity_room"]["weights"]["amenity"] == pytest.approx(0.15)

    # Kịch bản 2: User nhấn mạnh tiện nghi (include_amenity_overall=True + preferred_amenities)
    agent_amenity_weights = {"price": 0.25, "safety": 0.20, "semantic": 0.10, "amenity": 0.45}
    res_pref = rerank(
        [missing_amenity_room, good_room],
        user_pref={"max_price": 4_000_000, "preferred_amenities": ["aircon"], "include_amenity_overall": True},
        base_weights=agent_amenity_weights,
        limit=5,
    )
    assert res_pref[0][1]["id"] == "good_room"
    bd_pref = {item["id"]: bd for bd, item in res_pref}
    assert bd_pref["missing_amenity_room"]["parts"]["amenity"] == UNKNOWN_SCORE


def test_freshness_and_completeness_priority_in_rerank():
    """Kiểm thử 4 nhóm cho ưu tiên độ mới (posted_date) & độ đầy đủ thông tin:
    1. Happy path: 2 phòng cùng điểm MCDM, phòng mới đăng đầy đủ ảnh/diện tích/giá thắng phòng cũ & thiếu thông tin.
    2. Boundary: <= 7 ngày đạt 1.00; 30 ngày đạt 0.96; >= 90 ngày đạt 0.92; thiếu ngày đăng trung tính 0.97.
    3. Guardrail: hệ số chỉ là tinh chỉnh nhẹ [0.84..1.00], không làm phòng tệ mới đăng thắng phòng rất tốt đăng cũ.
    4. Negative/Corner: posted_date sai định dạng chuỗi, main_image placeholder, area_m2 <= 0 không gây crash.
    """
    from datetime import datetime, timedelta, timezone
    from app.services.reranker import _completeness_factor, _freshness_factor

    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    # Boundary độ mới
    assert _freshness_factor({"posted_date": now - timedelta(days=2)}, now_utc=now) == pytest.approx(1.0)
    assert _freshness_factor({"posted_date": now - timedelta(days=7)}, now_utc=now) == pytest.approx(1.0)
    assert _freshness_factor({"posted_date": now - timedelta(days=30)}, now_utc=now) == pytest.approx(0.96)
    assert _freshness_factor({"posted_date": now - timedelta(days=90)}, now_utc=now) == pytest.approx(0.92)
    assert _freshness_factor({"posted_date": now - timedelta(days=180)}, now_utc=now) == pytest.approx(0.92)
    assert _freshness_factor({"posted_date": None}, now_utc=now) == pytest.approx(0.97)
    # Naive datetime & ISO string & invalid string
    assert _freshness_factor({"posted_date": datetime(2026, 11, 16, 8, 0)}, now_utc=now) == pytest.approx(1.0)
    assert _freshness_factor({"posted_date": (now - timedelta(days=30)).isoformat()}, now_utc=now) == pytest.approx(0.96)
    assert _freshness_factor({"posted_date": "not-a-date"}, now_utc=now) == pytest.approx(0.97)

    # Completeness boundary & negative
    assert _completeness_factor({"images": ["https://img.test/1.jpg"], "area_m2": 25.0, "price_vnd": 3_500_000}) == pytest.approx(1.0)
    assert _completeness_factor({"main_image": "/property-placeholder.svg", "area_m2": 0, "price_vnd": None}) == pytest.approx(0.92)

    # So sánh trong rerank(): cùng cấu hình MCDM -> mới + đủ ảnh/diện tích thắng cũ + thiếu thông tin
    fresh_complete = {
        "id": "fresh_complete",
        "listing": {
            "id": "fresh_complete",
            "price_vnd": 3_500_000,
            "area_m2": 25.0,
            "images": ["https://img.test/a.jpg"],
            "posted_date": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "price_score": 0.85,
            "safety_score": 0.80,
            "amenity_overall": 0.80,
            "similarity_score": 0.75,
        },
    }
    stale_incomplete = {
        "id": "stale_incomplete",
        "listing": {
            "id": "stale_incomplete",
            "price_vnd": 3_500_000,
            "area_m2": None,
            "images": [],
            "posted_date": (datetime.now(timezone.utc) - timedelta(days=95)).isoformat(),
            "price_score": 0.85,
            "safety_score": 0.80,
            "amenity_overall": 0.80,
            "similarity_score": 0.75,
        },
    }
    res = rerank([stale_incomplete, fresh_complete], user_pref={"max_price": 4_000_000}, limit=5)
    assert res[0][1]["id"] == "fresh_complete"
    assert res[0][0]["quality_factor"] > res[1][0]["quality_factor"]

    # Guardrail: phòng chất lượng thấp mới đăng (0.40) KHÔNG thắng phòng tốt đăng cũ (0.90)
    bad_fresh = {
        "id": "bad_fresh",
        "listing": {
            "id": "bad_fresh",
            "price_vnd": 3_500_000,
            "area_m2": 25.0,
            "images": ["https://img.test/b.jpg"],
            "posted_date": datetime.now(timezone.utc).isoformat(),
            "price_score": 0.35,
            "safety_score": 0.30,
            "amenity_overall": 0.30,
            "similarity_score": 0.40,
        },
    }
    great_old = {
        "id": "great_old",
        "listing": {
            "id": "great_old",
            "price_vnd": 3_500_000,
            "area_m2": 25.0,
            "images": ["https://img.test/c.jpg"],
            "posted_date": (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
            "price_score": 0.92,
            "safety_score": 0.90,
            "amenity_overall": 0.90,
            "similarity_score": 0.88,
        },
    }
    res_guard = rerank([bad_fresh, great_old], user_pref={"max_price": 4_000_000}, limit=5)
    assert res_guard[0][1]["id"] == "great_old"


def test_budget_band_fit_prevents_5m_bias_when_searching_max_10m():
    """Khi người dùng tìm max_price=10tr (prefer_cheapest=False), căn hộ 8.5tr chất lượng cao phải xếp trên
    phòng trọ 4.5tr; còn khi bật prefer_cheapest=True hoặc đặt max_price=5tr thì phòng 4.5tr lên Top 1.
    """
    from app.services.reranker import _price_fit

    apartment_8_5m = {
        "id": "apt_8_5m",
        "listing": {
            "id": "apt_8_5m",
            "price_vnd": 8_500_000,
            "price_score": 0.25,
            "safety_score": 0.62,
            "amenity_overall": 0.85,
            "concept_scores": {"amenity_overall": 0.85},
            "similarity_score": 0.78,
        },
    }
    room_4_5m = {
        "id": "room_4_5m",
        "listing": {
            "id": "room_4_5m",
            "price_vnd": 4_500_000,
            "price_score": 0.47,
            "safety_score": 0.48,
            "amenity_overall": 0.58,
            "concept_scores": {"amenity_overall": 0.58},
            "similarity_score": 0.78,
        },
    }

    pref_10m = {"max_price": 10_000_000, "prefer_cheapest": False}
    assert _price_fit(apartment_8_5m["listing"], pref_10m) > _price_fit(room_4_5m["listing"], pref_10m)
    res_10m = rerank([room_4_5m, apartment_8_5m], user_pref=pref_10m, limit=5)
    assert res_10m[0][1]["id"] == "apt_8_5m"

    pref_cheapest_10m = {"max_price": 10_000_000, "prefer_cheapest": True}
    res_cheapest = rerank([room_4_5m, apartment_8_5m], user_pref=pref_cheapest_10m, limit=5)
    assert res_cheapest[0][1]["id"] == "room_4_5m"

    pref_5m = {"max_price": 5_000_000, "prefer_cheapest": False}
    res_5m = rerank([room_4_5m, apartment_8_5m], user_pref=pref_5m, limit=5)
    assert res_5m[0][1]["id"] == "room_4_5m"

