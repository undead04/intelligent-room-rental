"""Bộ kiểm thử Black-box độc lập cho MỐC 2 (Homigo Quality Testing).

Bao hàm đầy đủ 4 nhóm test cases theo chuẩn rigorous-testing:
1. Nhóm 1 (Happy Path):
   - Tra cứu POI Đại học 0 ms: "UIT", "Bách Khoa CS2", "ĐH Sư phạm Kỹ thuật" trả về đúng lat/lng với kind="point" ngay lập tức mà không gọi geocode bên ngoài.
   - Phòng thủ NLU: "tìm phòng khép kín", "wc riêng", "không chung chủ", "cho 2 bạn nữ", "cần tìm studio" đều tự động kích hoạt RoomType.SLEEPBOX trong patch.excluded_room_types.
2. Nhóm 2 (Edge cases):
   - Phòng từ Backend bị thiếu relationship (r.room_type is None) nhưng có r.room_type_id == 4 (hoặc listing["room_type_id"] = 4) -> check_hard_constraints phải loại bỏ triệt để và gán lý do chính xác.
   - Đảo chiều ý định: Khi người dùng tìm "ở ghép ký túc xá" hoặc "tìm sleepbox giá rẻ" -> RoomType.SLEEPBOX TUYỆT ĐỐI KHÔNG bị đưa vào excluded_room_types.
3. Nhóm 3 (Backend Reranker Price Fit Verification):
   - So sánh 2 căn phòng: Căn A (giá 2.0tr, ml_score = 0.55), Căn B (giá 3.8tr trong ngân sách 4.0tr, ml_score = 0.95).
   - Khi ở chế độ ưu tiên giá rẻ (weights["price"] = 0.40), xác minh điểm _price_fit của Căn A (rẻ thực tế) cao hơn rõ rệt so với Căn B (đắt tiền có deal hời).
4. Nhóm 4 (Failure / Fallback):
   - Tra cứu địa danh không có trong danh mục POI đại học (vd: "Chợ X", "Địa điểm lạ") -> fallback mượt mà sang geocode thông thường, không throw exception.
"""
import os
import sys
from types import SimpleNamespace
import pytest

# Đảm bảo import được backend và ai-agent
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from domain.enums import RoomType
from domain.schemas import RoomItem, UserPreferenceState
from intelligence.nlu import PreferencePatch, TurnAnalysis, _postprocess
from safety.grounding import check_hard_constraints
from tools.location_service import lookup_university_poi, resolve_location


# ============================================================================
# NHÓM 1: HAPPY PATH (POI RESOLUTION 0 MS & NLU SLEEPBOX DEFENSE)
# ============================================================================

def test_happy_path_resolve_university_pois_without_calling_geocode():
    """Nhóm 1:
    Các trường đại học phổ biến ('UIT', 'Bách Khoa CS2', 'ĐH Sư phạm Kỹ thuật')
    phải được phân giải toạ độ tức thì từ từ điển cục bộ (0 ms).
    Hàm geocode bên ngoài KHÔNG ĐƯỢC PHÉP bị gọi.
    """
    def strict_geocode(query, hint):
        raise AssertionError(f"Geocode bên ngoài bị gọi không cần thiết cho query: '{query}'")

    fake_admin_lookup = lambda *a, **kw: []

    # 1. UIT
    res_uit = resolve_location("UIT", kind=None, admin_lookup=fake_admin_lookup, geocode=strict_geocode)
    assert res_uit.kind == "point"
    assert res_uit.lat == pytest.approx(10.87, abs=0.01)
    assert res_uit.lng == pytest.approx(106.80, abs=0.01)

    # 2. Bách Khoa CS2
    res_bk2 = resolve_location("Bách Khoa CS2", kind="place", admin_lookup=fake_admin_lookup, geocode=strict_geocode)
    assert res_bk2.kind == "point"
    assert res_bk2.lat == pytest.approx(10.8804, abs=0.005)
    assert res_bk2.lng == pytest.approx(106.8056, abs=0.005)

    # 3. ĐH Sư phạm Kỹ thuật
    res_spkt = resolve_location("ĐH Sư phạm Kỹ thuật", kind="place", admin_lookup=fake_admin_lookup, geocode=strict_geocode)
    assert res_spkt.kind == "point"
    assert res_spkt.lat == pytest.approx(10.8506, abs=0.005)
    assert res_spkt.lng == pytest.approx(106.7720, abs=0.005)


def test_happy_path_nlu_sleepbox_decision_respected():
    """Nhóm 1: _postprocess tôn trọng hoàn toàn quyết định loại trừ/cho phép SLEEPBOX từ LLM."""
    a_excl = TurnAnalysis(intent="new_search", patch=PreferencePatch(excluded_room_types=[RoomType.SLEEPBOX]))
    assert _postprocess(a_excl, user_text="tìm phòng khép kín").patch.excluded_room_types == [RoomType.SLEEPBOX]

    a_plain = TurnAnalysis(intent="new_search", patch=PreferencePatch())
    assert _postprocess(a_plain, user_text="tìm phòng khép kín").patch.excluded_room_types == []


# ============================================================================
# NHÓM 2: EDGE CASES (BACKEND SCHEMA MISSING RELATIONSHIP & INTENT REVERSAL)
# ============================================================================

def test_edge_case_backend_missing_relationship_room_type_id_4():
    """Nhóm 2 (Edge case):
    Khi Backend trả về tin đăng bị thiếu relationship ORM (r.room_type is None)
    nhưng có r.room_type_id == 4 (hoặc listing['room_type_id'] = 4):
    1. RoomItem.from_backend_result phải chuẩn hóa khôi phục room_type = RoomType.SLEEPBOX.
    2. check_hard_constraints phải loại bỏ triệt để phòng này và gán lý do chính xác.
    """
    pref = UserPreferenceState(excluded_room_types=[RoomType.SLEEPBOX])

    # Case 2A: Dict listing từ Backend có room_type=None, room_type_id=4
    raw_item = {
        "listing": {
            "id": "orphan_sleepbox_1",
            "title": "Hộp ngủ cao cấp",
            "price_vnd": 1_800_000,
            "room_type": None,
            "room_type_id": 4,
        }
    }
    room_item_a = RoomItem.from_backend_result(raw_item)
    assert room_item_a.room_type == RoomType.SLEEPBOX
    assert room_item_a.room_type_id == 4

    valid_a, dropped_a = check_hard_constraints([room_item_a], pref)
    assert len(valid_a) == 0
    assert len(dropped_a) == 1
    assert dropped_a[0][0] == "orphan_sleepbox_1"
    assert "đã bị loại trừ" in dropped_a[0][1]

    # Case 2B: Đối tượng dạng object với room_type is None nhưng có room_type_id == 4
    room_item_b = SimpleNamespace(
        id="orphan_sleepbox_2",
        title="KTX giường tầng",
        priceNum=1_500_000,
        area_m2=12.0,
        room_type=None,
        room_type_id=4,
        concept_scores={},
    )
    valid_b, dropped_b = check_hard_constraints([room_item_b], pref)
    assert len(valid_b) == 0
    assert len(dropped_b) == 1
    assert dropped_b[0][0] == "orphan_sleepbox_2"
    assert "Ký túc xá / Sleepbox đã bị loại trừ" in dropped_b[0][1]


def test_edge_case_intent_reversal_shared_dorm_never_excluded():
    """Nhóm 2 (Đảo chiều ý định):
    Khi người dùng chủ động tìm kiếm hình thức ở ghép hoặc sleepbox giá rẻ:
    - 'ở ghép ký túc xá'
    - 'tìm sleepbox giá rẻ'
    - 'thuê giường tầng ktx'
    - 'tìm hộp ngủ giá rẻ'
    RoomType.SLEEPBOX TUYỆT ĐỐI KHÔNG ĐƯỢC PHÉP bị đưa vào patch.excluded_room_types!
    """
    shared_cues = [
        "ở ghép ký túc xá",
        "tìm sleepbox giá rẻ",
        "thuê giường tầng ktx",
        "tìm hộp ngủ giá rẻ",
    ]

    for cue in shared_cues:
        raw_analysis = TurnAnalysis(intent="new_search", patch=PreferencePatch())
        processed = _postprocess(raw_analysis, user_text=cue)
        assert RoomType.SLEEPBOX not in processed.patch.excluded_room_types, (
            f"Phát biểu '{cue}' tìm ở ghép/sleepbox nhưng lại bị đưa vào excluded_room_types: {processed.patch.excluded_room_types}"
        )


# ============================================================================
# NHÓM 3: BACKEND RERANKER PRICE FIT VERIFICATION
# ============================================================================

def test_price_fit_verification_cheap_room_vs_expensive_bargain():
    """Nhóm 3:
    So sánh 2 căn phòng trong ngân sách trần 4.0tr (max_price = 4_000_000):
    - Căn A: Giá 2.0tr (tiết kiệm 50% ngân sách), ml_score = 0.55 (điểm ML trung bình).
    - Căn B: Giá 3.8tr (tiết kiệm 5% ngân sách), ml_score = 0.95 (deal rất hời theo ML).

    1. Khi bật tường minh prefer_cheapest=True:
       - Xác minh điểm _price_fit của Căn A (rẻ thực tế) cao hơn rõ rệt so với Căn B (>= 0.15).
    2. Khi nói chung chung (không bật prefer_cheapest), kể cả khi weights['price'] = 0.40 do L1:
       - Căn B (deal hời ML 0.95) phải thắng Căn A (0.55), không bị bẫy tự bật prefer_cheap.
    """
    from app.services.reranker import _price_fit

    room_a = {"price_vnd": 2_000_000, "price_score": 0.55}
    room_b = {"price_vnd": 3_800_000, "price_score": 0.95}

    pref_cheapest = {"max_price": 4_000_000, "prefer_cheapest": True}
    priority_weights = {"price": 0.40}

    # Tính điểm price_fit khi ưu tiên giá rẻ tường minh
    score_a = _price_fit(room_a, user_pref=pref_cheapest, weights=priority_weights)
    score_b = _price_fit(room_b, user_pref=pref_cheapest, weights=priority_weights)

    assert score_a > score_b, f"Căn A ({score_a}) phải có price_fit cao hơn Căn B ({score_b})"
    assert score_a - score_b >= 0.15, (
        f"Chênh lệch điểm ({score_a - score_b}) phải >= 0.15 để đảm bảo căn rẻ chiến thắng"
    )

    # Khi nói chung chung (prefer_cheapest không bật), kể cả weights['price']=0.40,
    # Căn B (deal hời ML 0.95) vẫn phải vượt Căn A (0.55)
    pref_normal = {"max_price": 4_000_000}
    score_a_normal = _price_fit(room_a, user_pref=pref_normal, weights=priority_weights)
    score_b_normal = _price_fit(room_b, user_pref=pref_normal, weights=priority_weights)
    assert score_b_normal > score_a_normal
    assert score_b_normal >= 0.80


# ============================================================================
# NHÓM 4: FAILURE / FALLBACK (UNLISTED POI & GRACEFUL DEGRADATION)
# ============================================================================

def test_fallback_unlisted_poi_falls_back_to_geocode():
    """Nhóm 4:
    Khi tra cứu địa danh không có trong danh mục POI đại học cục bộ (vd: 'Chợ X', 'Địa điểm lạ'):
    1. lookup_university_poi trả về None (không đoán bừa).
    2. Fallback mượt mà sang geocode thông thường, không phát sinh ngoại lệ runtime.
    3. Nếu geocode gặp lỗi kết nối/mạng, resolve_location suy giảm an toàn thành unresolved_point.
    """
    # 1. Tra cứu trực tiếp từ điển
    assert lookup_university_poi("Chợ X") is None
    assert lookup_university_poi("Địa điểm lạ") is None

    # 2. Fallback sang geocode thành công
    geocode_calls = []
    def mock_geocode(query, hint):
        geocode_calls.append((query, hint))
        return {"lat": 10.75, "lng": 106.66}

    res = resolve_location(
        "Chợ X",
        kind="place",
        admin_lookup=lambda *a, **kw: [],
        geocode=mock_geocode,
    )
    assert len(geocode_calls) == 1
    assert geocode_calls[0][0] == "Chợ X"
    assert res.kind == "point"
    assert res.lat == 10.75
    assert res.lng == 106.66

    # 3. Fallback khi geocode bên ngoài bị lỗi kết nối
    def broken_geocode(query, hint):
        raise ConnectionError("Mất kết nối tới Geocoding Service")

    res_fail = resolve_location(
        "Địa điểm lạ",
        kind="place",
        admin_lookup=lambda *a, **kw: [],
        geocode=broken_geocode,
    )
    assert res_fail.kind == "unresolved_point"
    assert res_fail.lat is None
    assert res_fail.lng is None

