"""Bộ kiểm thử Black-box độc lập cho Adaptive Radius & Hard Constraint Verification (MỐC 1).

Bao gồm đủ 4 nhóm kiểm thử:
1. Happy path: Bán kính cơ sở mặc định 2.5km khi có toạ độ điểm mốc (point).
2. Strict constraint (Ca G2_03): Bán kính do người dùng chỉ định rõ (max_distance_km=2.0) được tôn trọng 100%, cấm tự nới lỏng.
3. Two-phase expansion: Thuật toán 2 pha (2.5km -> 3.5km -> 5.0km) tự kích hoạt khi valid_rooms < 3 và ghi trace.
4. Negative & Hard constraints: Ràng buộc trần giá (max_price) loại bỏ 100% phòng vượt ngân sách; proposed_budget là None khi không có khoảng trống thị trường (không tự nới giá ngầm +15%).
"""
import pytest
from domain.budget import MarketStats, propose_budget
from domain.schemas import RoomItem, UserPreferenceState
from graph.nodes.retrieval import make_retrieval_node
from safety.grounding import PRICE_FILTER_TOLERANCE, check_hard_constraints, verify_context_grounding
from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, Harness, nlu, raw_room


# ============================================================================
# 1. HAPPY PATH: BÁN KÍNH CƠ SỞ MẶC ĐỊNH 2.5KM KHI CÓ POINT
# ============================================================================

def test_default_base_radius_is_2_5km_for_point():
    """Test 1 (Happy Path):
    Khi người dùng tìm kiếm theo điểm mốc (point) mà không nói rõ bán kính,
    bán kính cơ sở mặc định của Phase 1 phải là 2.5km (thay vì 8.0km cũ).
    """
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="Đại học Bách Khoa TP.HCM", location_kind="place", max_price=4_000_000),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=[raw_room(1), raw_room(2), raw_room(3)])
    r = h.turn("tìm phòng quanh Đại học Bách Khoa")

    assert len(h.search_calls) == 1
    # Bán kính gửi tới Backend trong Phase 1 phải chính xác là 2.5km
    assert h.search_calls[0]["max_distance_km"] == 2.5
    assert len(r.rooms) == 3


def test_admin_location_has_no_distance_radius():
    """Happy Path:
    Khi tìm kiếm theo đơn vị hành chính (admin: Quận/Huyện/Phường),
    không áp đặt bán kính toạ độ (max_distance_km=None).
    """
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="Quận 10", location_kind="admin", district_id=771),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=[raw_room(1), raw_room(2), raw_room(3)])
    r = h.turn("tìm phòng quận 10")

    assert len(h.search_calls) == 1
    assert h.search_calls[0].get("max_distance_km") is None
    assert h.search_calls[0]["district_id"] == 761


# ============================================================================
# 2. STRICT CONSTRAINT: TÔN TRỌNG BÁN KÍNH NGƯỜI DÙNG CHỈ ĐỊNH (CA G2_03)
# ============================================================================

def test_user_specified_radius_strictly_respected_without_expansion():
    """Test 2 (Case G2_03 verification):
    Khi người dùng chỉ định rõ bán kính tìm kiếm (ví dụ max_distance_km = 2.0 quanh điểm mốc),
    hệ thống tôn trọng 100% con số này.
    Dù kết quả Phase 1 trả về ít hơn 3 phòng (chỉ có 1 phòng), hệ thống TUYỆT ĐỐI KHÔNG
    tự ý mở rộng bán kính lên 3.5km hay 5.0km.
    """
    def single_room_backend(args):
        # Trả về 1 phòng duy nhất
        return [raw_room(1, price=2_500_000, area=20.0)]

    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="Bách Khoa CS1", location_kind="place", max_distance_km=2.0),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=single_room_backend)
    r = h.turn("tìm phòng quanh Bách Khoa CS1 trong bán kính 2km")

    # Chỉ được gọi Backend đúng 1 lần với max_distance_km = 2.0
    assert len(h.search_calls) == 1
    assert h.search_calls[0]["max_distance_km"] == 2.0
    assert len(r.rooms) == 1

    # Không có bất kỳ trace event adaptive_radius_expansion nào
    expansion_events = [e for e in r.trace_events if e.get("type") == "adaptive_radius_expansion"]
    assert len(expansion_events) == 0


# ============================================================================
# 3. TWO-PHASE ADAPTIVE RADIUS EXPANSION (2.5KM -> 3.5KM -> 5.0KM)
# ============================================================================

def test_two_phase_expansion_stops_at_3_5km():
    """Test 3a (Thuật toán 2 pha - Dừng ở 3.5km):
    - Phase 1 (2.5km): Chỉ tìm được 1 phòng (< 3 phòng).
    - Phase 2 (mở rộng lên 3.5km): Tìm được 3 phòng (>= 3 phòng).
    Kiểm chứng:
    + Đã kích hoạt 2 lần gọi search: lần đầu 2.5km, lần hai 3.5km.
    + Dừng ngay tại 3.5km, KHÔNG mở rộng tiếp lên 5.0km.
    + Trace ghi nhận đúng 1 event `adaptive_radius_expansion` từ 2.5 lên 3.5km.
    """
    def dynamic_rooms(args):
        rad = args.get("max_distance_km")
        if rad == 2.5:
            return [raw_room(1, price=2_500_000)]
        elif rad == 3.5:
            return [
                raw_room(1, price=2_500_000),
                raw_room(2, price=2_700_000),
                raw_room(3, price=2_900_000),
            ]
        return [raw_room(i) for i in range(1, 6)]

    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="Bách Khoa", location_kind="place"),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=dynamic_rooms)
    r = h.turn("tìm phòng gần Bách Khoa")

    assert len(h.search_calls) == 2
    assert h.search_calls[0]["max_distance_km"] == 2.5
    assert h.search_calls[1]["max_distance_km"] == 3.5
    assert len(r.rooms) == 3

    # Kiểm tra event trace
    adaptive_events = [e for e in r.trace_events if e.get("type") == "adaptive_radius_expansion"]
    assert len(adaptive_events) == 1
    assert adaptive_events[0]["from_radius"] == 2.5
    assert adaptive_events[0]["to_radius"] == 3.5
    assert adaptive_events[0]["valid_rooms_before"] == 1


def test_two_phase_expansion_continues_to_5_0km():
    """Test 3b (Thuật toán 2 pha - Tiếp tục mở rộng lên 5.0km):
    - Phase 1 (2.5km): 0 phòng (< 3).
    - Phase 2 Bước 1 (3.5km): Vẫn chỉ có 1 phòng (< 3).
    - Phase 2 Bước 2 (5.0km): Tìm được 4 phòng (>= 3).
    Kiểm chứng:
    + Gọi search 3 lần: 2.5km -> 3.5km -> 5.0km.
    + Trace ghi nhận 2 event `adaptive_radius_expansion` theo thứ tự.
    + Kết quả cuối cùng trả về đủ 4 phòng.
    """
    def dynamic_rooms(args):
        rad = args.get("max_distance_km")
        if rad == 2.5:
            return []
        elif rad == 3.5:
            return [raw_room(1, price=2_600_000)]
        elif rad == 5.0:
            return [
                raw_room(1, price=2_600_000),
                raw_room(2, price=2_800_000),
                raw_room(3, price=3_000_000),
                raw_room(4, price=3_200_000),
            ]
        return []

    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="Bách Khoa", location_kind="place"),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=dynamic_rooms)
    r = h.turn("tìm phòng quanh Bách Khoa")

    assert len(h.search_calls) == 3
    assert h.search_calls[0]["max_distance_km"] == 2.5
    assert h.search_calls[1]["max_distance_km"] == 3.5
    assert h.search_calls[2]["max_distance_km"] == 5.0
    assert len(r.rooms) == 4

    adaptive_events = [e for e in r.trace_events if e.get("type") == "adaptive_radius_expansion"]
    assert len(adaptive_events) == 2
    assert adaptive_events[0]["from_radius"] == 2.5
    assert adaptive_events[0]["to_radius"] == 3.5
    assert adaptive_events[1]["from_radius"] == 3.5
    assert adaptive_events[1]["to_radius"] == 5.0


# ============================================================================
# 4. NEGATIVE & HARD CONSTRAINTS (PRICE CEILING & PROPOSED BUDGET)
# ============================================================================

def test_hard_constraint_price_filter_drops_overpriced_rooms():
    """Test 4a (Negative / Hard Constraint - Giá trần max_price):
    Bất kỳ phòng nào có giá vượt quá pref.max_price (kèm sai số cho phép 2% tolerance)
    đều phải bị Context Grounding loại bỏ hoàn toàn, không lọt vào danh sách kết quả.
    """
    pref = UserPreferenceState(max_price=3_000_000)
    tolerance_ceiling = 3_000_000 * (1 + PRICE_FILTER_TOLERANCE)  # 3.060.000đ

    rooms = [
        RoomItem(id="r1", title="Phòng 1", price="2.5 triệu", priceNum=2_500_000),
        RoomItem(id="r2", title="Phòng 2", price="3.0 triệu", priceNum=3_000_000),
        RoomItem(id="r3", title="Phòng 3", price="3.05 triệu", priceNum=3_050_000),  # Dưới 3.06tr -> Hợp lệ
        RoomItem(id="r4", title="Phòng 4", price="3.1 triệu", priceNum=3_100_000),   # Vượt 3.06tr -> Loại
        RoomItem(id="r5", title="Phòng 5", price="4.5 triệu", priceNum=4_500_000),   # Vượt xa -> Loại
    ]

    valid, dropped = check_hard_constraints(rooms, pref)
    valid_ids = [r.id for r in valid]

    assert valid_ids == ["r1", "r2", "r3"]
    assert "r4" not in valid_ids
    assert "r5" not in valid_ids

    dropped_dict = dict(dropped)
    assert "r4" in dropped_dict
    assert "r5" in dropped_dict
    assert "vượt ngân sách" in dropped_dict["r4"]
    assert "vượt ngân sách" in dropped_dict["r5"]

    # Kiểm tra End-to-end với Harness
    def backend_overpriced(args):
        return [
            raw_room(1, price=2_800_000),
            raw_room(2, price=3_500_000),  # Vượt ngân sách
            raw_room(3, price=4_200_000),  # Vượt ngân sách
        ]

    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="UIT", location_kind="place", max_price=3_000_000),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=backend_overpriced)
    r = h.turn("tìm phòng dưới 3 triệu ở UIT")

    # Chỉ còn đúng 1 phòng hợp lệ
    assert len(r.rooms) == 1
    assert r.rooms[0].priceNum <= tolerance_ceiling


def test_no_market_gap_leaves_proposed_budget_none():
    """Test 4b (Negative / Market Budget Proposal):
    Khi không có khoảng cách thị trường (ngân sách người dùng đáp ứng hoặc không có số liệu thị trường),
    proposed_budget BẮT BUỘC phải là None (tuyệt đối không tự nới giá ngầm +15%).
    """
    # 1. Kiểm tra unit logic propose_budget:
    # Ngân sách 3.0tr, giá sàn thị trường 2.8tr -> ngân sách >= 85% giá sàn -> Không có khoảng trống (is_market_gap = False)
    market = MarketStats(min_price=2_800_000, avg_price=3_500_000, total_listings=40)
    proposal = propose_budget(user_max=3_000_000, market=market)

    assert proposal is not None
    assert proposal.is_market_gap is False

    # 2. Kiểm tra verify_context_grounding khi không có phòng và is_market_gap = False
    fake_market_fetcher = lambda **kw: {
        "minimum_price_vnd": 2_800_000,
        "average_price_vnd": 3_500_000,
        "total_listings": 40,
    }
    pref = UserPreferenceState(max_price=3_000_000)
    res = verify_context_grounding([], preferences=pref, market_fetcher=fake_market_fetcher)

    # proposed_budget BẮT BUỘC phải là None!
    assert res.proposed_budget is None
    assert res.is_market_gap is False
    assert res.market_context.proposed_budget is None
    # Xác nhận không hề có mức giá nới ngầm 3.45tr (+15%)
    assert res.proposed_budget != 3_450_000

    # 3. Kiểm tra End-to-end với Harness khi kết quả rỗng
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="UIT", location_kind="place", max_price=3_000_000),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=[], market=fake_market_fetcher)
    r = h.turn("tìm phòng 3 triệu ở UIT")

    assert h.session.proposed_budget is None


# ============================================================================
# 5. CORNER CASES: EXPANSION INTERACTION WITH HARD CONSTRAINTS
# ============================================================================

def test_adaptive_expansion_accounts_for_hard_constraint_filtering():
    """Corner Case:
    Tại Phase 1 (2.5km), Backend trả về 3 phòng, nhưng có 2 phòng bị loại do vượt giá trần (max_price),
    nên chỉ còn 1 valid room (< 3).
    Hệ thống phải tự động nhận biết valid_rooms < 3 và kích hoạt mở rộng sang Phase 2 (3.5km).
    """
    def dynamic_rooms(args):
        rad = args.get("max_distance_km")
        if rad == 2.5:
            # 3 phòng nhưng 2 phòng vượt 3 triệu -> chỉ 1 valid room
            return [
                raw_room(1, price=2_800_000),
                raw_room(2, price=3_800_000),
                raw_room(3, price=4_000_000),
            ]
        elif rad == 3.5:
            # Mở rộng ra 3.5km tìm được thêm 2 phòng giá tốt
            return [
                raw_room(1, price=2_800_000),
                raw_room(4, price=2_900_000),
                raw_room(5, price=2_700_000),
            ]
        return []

    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu(location_text="UIT", location_kind="place", max_price=3_000_000),
    ).on("Advice", GOOD_ADVICE)

    h = Harness(llm, rooms=dynamic_rooms)
    r = h.turn("tìm phòng dưới 3 triệu gần UIT")

    # Do Phase 1 chỉ có 1 phòng hợp lệ sau lọc cứng, hệ thống phải mở rộng sang 3.5km
    assert len(h.search_calls) == 2
    assert h.search_calls[0]["max_distance_km"] == 2.5
    assert h.search_calls[1]["max_distance_km"] == 3.5
    assert len(r.rooms) == 3
    assert all(rm.priceNum <= 3_000_000 * (1 + PRICE_FILTER_TOLERANCE) for rm in r.rooms)
