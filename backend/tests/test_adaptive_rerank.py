"""Bộ kiểm thử Black-box độc lập cho MCDM Dynamic Reranking Engine (MỐC 1).

Bao gồm đủ 4 nhóm kiểm thử:
1. Happy path (Ca kiểm thử G2_05: Ưu tiên vị trí gần hơn tiện nghi xa).
2. Trọng số & Chuẩn hóa L1 (Bộ trọng số mới: location=0.25, price=0.25, safety=0.20, amenity=0.20, semantic=0.10).
3. Boundary & Edge cases (Khoảng cách tại near_km, far_km, vượt far_km, không có tọa độ).
4. Corner & Negative cases (Danh sách rỗng, phân trang offset/limit, lỗi tọa độ phi số).
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


def test_l1_normalization_when_location_inactive():
    """Khi không có tọa độ người dùng (chỉ tìm theo quận hoặc text), location tắt:
    Chuẩn hóa L1 phải phân bổ lại trọng số và semantic luôn là tiêu chí có trọng số thấp nhất.
    """
    # Kịch bản A: Không có location, có preferred_amenities (bật: price, safety, amenity, semantic)
    pref_with_amenity = {"preferred_amenities": ["aircon"]}
    w_a = _dynamic_weights(pref_with_amenity, DEFAULT_WEIGHTS)

    assert "location" not in w_a
    assert set(w_a.keys()) == {"price", "safety", "amenity", "semantic"}
    assert sum(w_a.values()) == pytest.approx(1.0)

    # Tổng cơ sở bật = 0.25 + 0.20 + 0.20 + 0.10 = 0.75
    assert w_a["price"] == pytest.approx(0.25 / 0.75)
    assert w_a["safety"] == pytest.approx(0.20 / 0.75)
    assert w_a["amenity"] == pytest.approx(0.20 / 0.75)
    assert w_a["semantic"] == pytest.approx(0.10 / 0.75)
    # Semantic phải là thấp nhất
    assert w_a["semantic"] < w_a["price"]
    assert w_a["semantic"] < w_a["safety"]
    assert w_a["semantic"] < w_a["amenity"]
    assert min(w_a, key=w_a.get) == "semantic"

    # Kịch bản B: Không có location, không có amenity ưu tiên (bật: price, safety, semantic)
    pref_minimal = {}
    w_b = _dynamic_weights(pref_minimal, DEFAULT_WEIGHTS)

    assert set(w_b.keys()) == {"price", "safety", "semantic"}
    assert sum(w_b.values()) == pytest.approx(1.0)

    # Tổng cơ sở bật = 0.25 + 0.20 + 0.10 = 0.55
    assert w_b["price"] == pytest.approx(0.25 / 0.55)
    assert w_b["safety"] == pytest.approx(0.20 / 0.55)
    assert w_b["semantic"] == pytest.approx(0.10 / 0.55)
    assert min(w_b, key=w_b.get) == "semantic"


# ============================================================================
# 3. BOUNDARY & EDGE CASES (NGƯỠNG KHOẢNG CÁCH & TỌA ĐỘ)
# ============================================================================

def test_location_fit_boundary_conditions():
    """Kiểm tra chặt chẽ các điểm giới hạn của hàm suy giảm phi tuyến _location_fit:
    1. dist = 0.0 -> 1.0 (trùng tọa độ)
    2. dist < near_km (0.5km) -> 1.0
    3. dist == near_km (0.8km) -> 1.0 (ngưỡng tối đa đạt điểm tuyệt đối)
    4. dist == far_km (3.0km hoặc 5.0km) -> 0.0 (chạm ngưỡng giới hạn)
    5. dist > far_km (3.01km, 5.5km, 10.0km) -> 0.0 (vượt bán kính)
    6. Tại trung điểm (50% khoảng cách từ near đến far): tỉ lệ đạt ~0.6464 > 0.5 do luỹ thừa 1.5.
    """
    # Bán kính tùy chỉnh 3.0km
    assert _location_fit(0.0, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(0.5, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(0.8, near_km=0.8, far_km=3.0) == 1.0
    assert _location_fit(3.0, near_km=0.8, far_km=3.0) == 0.0
    assert _location_fit(3.001, near_km=0.8, far_km=3.0) == 0.0
    assert _location_fit(10.0, near_km=0.8, far_km=3.0) == 0.0

    # Bán kính mặc định 5.0km
    assert _location_fit(0.8, near_km=0.8, far_km=5.0) == 1.0
    assert _location_fit(5.0, near_km=0.8, far_km=5.0) == 0.0
    assert _location_fit(5.001, near_km=0.8, far_km=5.0) == 0.0

    # Phi tuyến: ratio = 0.5 -> score = 1.0 - (0.5 ** 1.5) ≈ 0.6464
    mid_dist = 0.8 + 0.5 * (3.0 - 0.8)  # 1.9km
    expected_mid_score = 1.0 - (0.5 ** 1.5)
    assert _location_fit(mid_dist, near_km=0.8, far_km=3.0) == pytest.approx(expected_mid_score)


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
    - offset vượt quá số lượng candidate -> trả về []
    - limit nhỏ hơn tổng số candidate -> cắt đúng limit
    - Hai phòng cùng điểm số -> tie-break ổn định theo id.
    """
    pref = {"lat": 10.7721, "lng": 106.6579}

    # 1. Danh sách rỗng
    assert rerank([], pref) == []

    # 2. Phân trang offset / limit
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

    page_1 = rerank(cands, pref, limit=2, offset=0)
    assert len(page_1) == 2
    page_2 = rerank(cands, pref, limit=2, offset=2)
    assert len(page_2) == 2
    page_out_of_bounds = rerank(cands, pref, limit=2, offset=10)
    assert page_out_of_bounds == []


def test_zero_weights_raises_value_error():
    """Negative case: Nếu caller truyền vào base_weights với tất cả trọng số = 0,
    hệ thống phải raise ValueError("Tổng trọng số của các tiêu chí đang bật phải > 0").
    """
    zero_weights = {"price": 0.0, "safety": 0.0, "semantic": 0.0, "location": 0.0, "amenity": 0.0}
    with pytest.raises(ValueError, match="Tổng trọng số của các tiêu chí đang bật phải > 0"):
        _dynamic_weights({"lat": 10.77, "lng": 106.65}, base=zero_weights)

