"""Black-box Integration & Unit Tests cho Mốc 2 (AI-Agent Generalization, Grounding & Clean Code).

Tuân thủ nghiêm ngặt quy chuẩn kiểm thử độc lập tại .gemini/skills/rigorous-testing/SKILL.md:
1. Nhóm 1: Happy Path
   - Multi-RoomType (allowed_room_types), computed field room_type_id trên UserPreferenceState & RoomItem
   - Đủ 17 Concept Tags (washing_machine, camera, fingerprint_lock, no_shared_landlord, safe_area, guard)
   - check_hard_constraints kiểm tra allowed_room_types VÀ chuỗi Haversine -> Amenities tuần tự (không bị bug elif)
   - verify_answer_grounding Scope Binding nhận diện chính xác nhãn 'Top 1', 'Top 2' và bắt lỗi gán nhầm giá/diện tích
   - location_service.resolve_admin phân giải thành công cấp ward khi người dùng nhập 'Phường, Tỉnh/Thành' bỏ qua Quận/TP Thủ Đức
2. Nhóm 2: Boundary & Edge Cases
   - Domain Generalization trong NLU _postprocess: tự động loại trừ SLEEPBOX khi có nhu cầu phòng riêng biệt (diện tích >= 15m2, nhiều người ở, tiện ích riêng), KHÔNG loại trừ khi chủ động nhận KTX/giường tầng
   - search_rooms_api fallback query rỗng/khoảng trắng, clamp max_distance_km trong [0.5, 50.0], không sinh key room_types thừa
   - understand.py rollback hỗ trợ tiếng Việt có dấu nhờ strip_accents hai vế, từ khóa phủ định không kích hoạt nhầm multiplier
3. Nhóm 3: State Mutation & Isolation
   - retrieval_node bảo toàn last_search_args['max_distance_km'] khi mở rộng Adaptive Radius gặp lỗi mạng (không bị ghi đè bẩn)
   - SessionData.record_preference_snapshot giới hạn tối đa 20 snapshots và bảo toàn 100% snapshot gốc của lượt 1
4. Nhóm 4: Persistence & Resource Cleanup (SQLite SessionStore trên Windows)
   - PersistentSessionStore đóng triệt để mọi sqlite3.Connection trong Generator try/finally, cho phép xóa file SQLite trực tiếp trên Windows không bị [WinError 32].
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from domain.enums import Amenity, RoomType
from domain.schemas import RoomItem, UserPreferenceState
from intelligence.nlu import (
    PreferencePatch,
    TurnAnalysis,
    _postprocess,
    apply_patch,
)
from intelligence.understand import (
    _build_revert_preferences,
    _has_unnegated_keyword,
    interpret_turn,
)
from safety.grounding import (
    check_hard_constraints,
    verify_answer_grounding,
)
from tools.location_service import resolve_admin
from tools.housing_tools import search_rooms_api
from graph.nodes.retrieval import make_retrieval_node
from core.session_store import SessionData, PersistentSessionStore
from utils.text import strip_accents
from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, Harness, nlu, raw_room


# ==============================================================================
# NHÓM 1: HAPPY PATH (MULTI-ROOMTYPE, 17 TAGS, SCOPE BINDING, WARD FALLBACK)
# ==============================================================================

def test_user_preference_multi_room_types_and_computed_fields():
    """Nhóm 1: UserPreferenceState hỗ trợ allowed_room_types, apply_patch chuẩn hóa chính xác,
    và @computed_field room_type_id xuất hiện đầy đủ trong .model_dump().
    """
    pref = UserPreferenceState()

    # 1. Áp patch với nhiều loại phòng được phép
    patch_multi = PreferencePatch(room_types_allow=["ROOM", "STUDIO"])
    p_multi = apply_patch(pref, patch_multi)

    assert p_multi.allowed_room_types == [RoomType.ROOM, RoomType.STUDIO]
    assert p_multi.room_type is None, "Khi có >1 loại phòng cho phép, room_type đơn trị phải là None"

    dump_multi = p_multi.model_dump()
    assert "room_type_id" in dump_multi
    assert dump_multi["room_type_id"] is None

    # 2. Áp patch với 1 loại phòng duy nhất được phép
    patch_single = PreferencePatch(room_types_allow=["STUDIO"])
    p_single = apply_patch(pref, patch_single)

    assert p_single.allowed_room_types == [RoomType.STUDIO]
    assert p_single.room_type == RoomType.STUDIO
    dump_single = p_single.model_dump()
    assert dump_single["room_type_id"] == 2

    # 3. RoomItem có computed_field room_type_id
    item_room = RoomItem(
        id="room_item_test_1",
        title="Phòng trọ cao cấp",
        price="3.5 triệu/tháng",
        priceNum=3_500_000.0,
        room_type=RoomType.ROOM,
    )
    item_dump = item_room.model_dump()
    assert "room_type_id" in item_dump
    assert item_dump["room_type_id"] == 1

    item_none = RoomItem(
        id="room_item_test_2",
        title="Phòng trọ chưa rõ loại",
        price="3.5 triệu/tháng",
        priceNum=3_500_000.0,
        room_type=None,
    )
    assert item_none.room_type_id is None
    assert item_none.model_dump()["room_type_id"] is None


def test_room_item_from_backend_17_concept_tags():
    """Nhóm 1: RoomItem.from_backend_result với concept_scores trích xuất đầy đủ 17 nhãn tiện ích
    mới bao gồm máy giặt, camera, khóa vân tay, không chung chủ, khu an ninh, bảo vệ 24/7.
    """
    backend_payload = {
        "listing": {
            "id": "item_full_concept_tags",
            "title": "Căn hộ dịch vụ tiện nghi đầy đủ",
            "price_vnd": 4_500_000.0,
            "concept_scores": {
                "washing_machine": 0.90,
                "camera": 0.85,
                "fingerprint_lock": 0.95,
                "no_shared_landlord": 0.80,
                "safe_area": 0.92,
                "guard": 0.88,
                "aircon": 0.30,  # Dưới ngưỡng 0.75 -> không được xuất hiện
            },
        },
        "explain_match": {},
        "match_score": 0.9,
    }

    room = RoomItem.from_backend_result(backend_payload)

    # 6 nhãn tiện ích mới được bổ sung trong Mốc 2 phải xuất hiện khi điểm ML >= 0.75
    assert "Có máy giặt" in room.inferred_tags
    assert "Camera an ninh" in room.inferred_tags
    assert "Khóa vân tay" in room.inferred_tags
    assert "Không chung chủ" in room.inferred_tags
    assert "Khu an ninh" in room.inferred_tags
    assert "Bảo vệ 24/7" in room.inferred_tags

    # Tiện ích có điểm dưới ngưỡng 0.75 không được xuất hiện trong inferred_tags
    assert "Có máy lạnh" not in room.inferred_tags


def test_check_hard_constraints_allowed_room_types_and_haversine_amenity_sequence():
    """Nhóm 1: check_hard_constraints giữ đúng allowed_room_types, loại bỏ loại phòng ngoài tập;
    đồng thời kiểm tra chuỗi Haversine -> Amenities tuần tự (không bị bug elif nuốt mất kiểm tra tiện ích!).
    """
    # 1. Kiểm thử allowed_room_types
    pref_rt = UserPreferenceState(allowed_room_types=[RoomType.ROOM, RoomType.APARTMENT])
    r_room = RoomItem(id="r1", title="Phòng trọ", price="3tr", priceNum=3_000_000, room_type=RoomType.ROOM)
    r_studio = RoomItem(id="r2", title="Studio", price="3tr", priceNum=3_000_000, room_type=RoomType.STUDIO)
    r_apt = RoomItem(id="r3", title="Chung cư", price="3tr", priceNum=3_000_000, room_type=RoomType.APARTMENT)
    r_sleepbox = RoomItem(id="r4", title="Sleepbox", price="1.5tr", priceNum=1_500_000, room_type=RoomType.SLEEPBOX)

    valid_rts, dropped_rts = check_hard_constraints([r_room, r_studio, r_apt, r_sleepbox], pref_rt)
    valid_rt_ids = [r.id for r in valid_rts]

    assert "r1" in valid_rt_ids
    assert "r3" in valid_rt_ids
    assert "r2" not in valid_rt_ids
    assert "r4" not in valid_rt_ids

    # 2. Kiểm chứng không bị bug 'elif' nuốt mất kiểm tra tiện ích khi khoảng cách hợp lệ
    center_lat, center_lng = 10.8700, 106.8031
    pref_loc_amenity = UserPreferenceState(
        lat=center_lat,
        lng=center_lng,
        max_distance_km=2.0,
        amenities=[Amenity.AIRCON],
    )

    # Phòng A: Cách tâm 0.3 km (nằm TRONG bán kính 2.0 km), nhưng thiếu máy lạnh (concept_scores aircon = 0.1)
    # Nếu có bug 'elif': khoảng cách hợp lệ sẽ bỏ qua kiểm tra tiện ích -> Phòng A lọt sai!
    # Code chuẩn: khoảng cách hợp lệ tiếp tục kiểm tra tiện ích -> Phòng A PHẢI BỊ LOẠI BỎ!
    r_close_no_aircon = RoomItem(
        id="r_close_no_aircon",
        title="Phòng trọ gần tâm thiếu máy lạnh",
        price="3tr",
        priceNum=3_000_000,
        lat=10.8720,
        lng=106.8040,
        concept_scores={"aircon": 0.1},
    )

    # Phòng B: Cách tâm 0.3 km và có máy lạnh đầy đủ
    r_close_has_aircon = RoomItem(
        id="r_close_has_aircon",
        title="Phòng trọ gần tâm có máy lạnh",
        price="3tr",
        priceNum=3_000_000,
        lat=10.8720,
        lng=106.8040,
        concept_scores={"aircon": 0.9},
    )

    valid_seq, dropped_seq = check_hard_constraints([r_close_no_aircon, r_close_has_aircon], pref_loc_amenity)
    valid_seq_ids = [r.id for r in valid_seq]

    assert "r_close_has_aircon" in valid_seq_ids
    assert "r_close_no_aircon" not in valid_seq_ids, "Phòng thiếu tiện ích bắt buộc PHẢI bị loại bỏ dù khoảng cách hợp lệ"
    assert any(d[0] == "r_close_no_aircon" and "thiếu tiện ích bắt buộc" in d[1] for d in dropped_seq)


def test_verify_answer_grounding_scope_binding_top_k():
    """Nhóm 1: verify_answer_grounding Scope Binding nhận diện chính xác nhãn 'Top 1', 'Top 2'
    và phát hiện lỗi ảo giác khi LLM gán nhầm giá/diện tích giữa các phòng.
    """
    r1 = RoomItem(
        id="room_101",
        rank=1,
        title="Phòng trọ Linh Trung",
        price="2.8 triệu/tháng",
        priceNum=2_800_000.0,
        area_m2=20.0,
    )
    r2 = RoomItem(
        id="room_202",
        rank=2,
        title="Phòng trọ Linh Xuân",
        price="3.5 triệu/tháng",
        priceNum=3_500_000.0,
        area_m2=30.0,
    )

    # Ca 1: LLM gán nhầm giá của Top 2 cho Top 1
    wrong_price_text = "Top 1 có giá 3.5 triệu/tháng rất phù hợp ngân sách của bạn."
    res_wrong = verify_answer_grounding(wrong_price_text, [r1, r2])

    assert res_wrong.is_grounded is False
    assert any("Gán nhầm số tiền" in issue for issue in res_wrong.issues)
    assert any("3.5 triệu" in issue for issue in res_wrong.issues)

    # Ca 2: LLM gán nhầm diện tích của Top 2 cho Top 1
    wrong_area_text = "Top 1 có diện tích 30m2 rất rộng rãi."
    res_area_wrong = verify_answer_grounding(wrong_area_text, [r1, r2])

    assert res_area_wrong.is_grounded is False
    assert any("Gán nhầm diện tích" in issue for issue in res_area_wrong.issues)

    # Ca 3: LLM gán đúng thông số cho Top 1 và Top 2
    correct_text = "Top 1 có giá 2.8 triệu/tháng với diện tích 20m2, còn Top 2 có giá 3.5 triệu/tháng rộng 30m2."
    res_correct = verify_answer_grounding(correct_text, [r1, r2])

    assert res_correct.is_grounded is True
    assert len(res_correct.issues) == 0


def test_location_service_resolve_admin_ward_fallback():
    """Nhóm 1: location_service.resolve_admin phân giải thành công cấp ward khi người dùng nhập
    'Phường, Tỉnh/Thành' (bỏ qua cấp Quận/Huyện/TP Thủ Đức).
    """
    def mock_admin_lookup(level: str, name: str, city_id: int | None = None, district_id: int | None = None):
        if level == "city":
            return [{"id": 79, "name": "Thành phố Hồ Chí Minh"}]
        if level == "district":
            return []  # Không tìm thấy quận mang tên Linh Trung
        if level == "ward":
            return [{"id": 26812, "district_id": 769, "city_id": 79, "name": "Phường Linh Trung"}]
        return []

    # Nhập 'Linh Trung, TP.HCM' (bỏ qua TP Thủ Đức)
    res = resolve_admin("Linh Trung, TP.HCM", mock_admin_lookup)

    assert res.kind == "admin"
    assert res.level == "ward"
    assert res.city_id == 79
    assert res.ward_id == 26812
    assert res.district_id == 769


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES (SLEEPBOX GENERALIZATION, CLAMPING & ACCENTS)
# ==============================================================================

def test_nlu_postprocess_domain_generalization_sleepbox():
    """Nhóm 2: NLU _postprocess tổng quát hóa theo miền bài toán:
    - Yêu cầu không gian riêng (diện tích >= 15m2, nhiều người ở, tiện ích riêng) -> tự loại trừ SLEEPBOX
    - Người dùng chủ động tìm KTX/giường tầng -> KHÔNG loại trừ SLEEPBOX.
    """
    # 1. Yêu cầu diện tích phòng riêng (min_area = 25m2 >= 15m2)
    a1 = TurnAnalysis(intent="new_search", patch=PreferencePatch(min_area=25.0))
    _postprocess(a1, user_text="tìm phòng rộng trên 25m2", n_rooms=0)
    assert RoomType.SLEEPBOX in a1.patch.room_types_exclude

    # 2. Yêu cầu cho nhóm người ở ("hai vợ chồng", "nhóm 3 người")
    a2 = TurnAnalysis(intent="new_search", patch=PreferencePatch())
    _postprocess(a2, user_text="hai vợ chồng cần thuê phòng ở lâu dài", n_rooms=0)
    assert RoomType.SLEEPBOX in a2.patch.room_types_exclude

    a3 = TurnAnalysis(intent="new_search", patch=PreferencePatch())
    _postprocess(a3, user_text="nhóm 3 bạn sinh viên tìm chỗ ở gần trường", n_rooms=0)
    assert RoomType.SLEEPBOX in a3.patch.room_types_exclude

    # 3. Yêu cầu tiện ích không gian riêng biệt (nuôi thú cưng, ban công)
    a4 = TurnAnalysis(intent="new_search", patch=PreferencePatch(amenities_add=[Amenity.PET_ALLOWED]))
    _postprocess(a4, user_text="tìm phòng cho nuôi mèo thoải mái", n_rooms=0)
    assert RoomType.SLEEPBOX in a4.patch.room_types_exclude

    # 4. Người dùng CHỦ ĐỘNG tìm KTX / Sleepbox -> KHÔNG loại trừ SLEEPBOX
    a5 = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(room_types_allow=[RoomType.SLEEPBOX, RoomType.ROOM]),
    )
    _postprocess(a5, user_text="tìm ktx hoặc phòng trọ giá sinh viên", n_rooms=0)
    assert RoomType.SLEEPBOX not in a5.patch.room_types_exclude


def test_search_rooms_api_edge_and_boundary_clamping():
    """Nhóm 2: search_rooms_api fallback an toàn khi query rỗng, clamp max_distance_km trong [0.5, 50.0],
    và không gửi key 'room_types' thừa khi không có.
    """
    captured_payloads = []

    def mock_request(method, path, json=None, **kwargs):
        captured_payloads.append(json)
        return {"ok": True, "data": []}

    with patch("tools.housing_tools.request", side_effect=mock_request):
        # 1. query rỗng hoặc khoảng trắng -> fallback thành 'phòng trọ'
        search_rooms_api({"query": "   ", "limit": 5})
        assert captured_payloads[-1]["query"] == "phòng trọ"

        # 2. max_distance_km = 0.1 < 0.5 -> clamp lên 0.5
        search_rooms_api({"query": "phòng trọ", "max_distance_km": 0.1})
        assert captured_payloads[-1]["max_distance_km"] == 0.5

        # 3. max_distance_km = 120.0 > 50.0 -> clamp xuống 50.0
        search_rooms_api({"query": "phòng trọ", "max_distance_km": 120.0})
        assert captured_payloads[-1]["max_distance_km"] == 50.0

        # 4. Không truyền room_types -> không sinh key 'room_types' trong json body
        search_rooms_api({"query": "phòng trọ"})
        assert "room_types" not in captured_payloads[-1]

        # 5. Truyền room_types hợp lệ -> sinh danh sách string value
        search_rooms_api({"query": "phòng trọ", "room_types": [RoomType.ROOM, RoomType.STUDIO]})
        assert captured_payloads[-1]["room_types"] == ["ROOM", "STUDIO"]


def test_understand_rollback_accents_and_unnegated_keywords():
    """Nhóm 2: understand.py rollback nhận diện đúng tiện ích tiếng Việt có dấu nhờ strip_accents hai vế,
    và từ khóa phủ định 'không cần phòng xịn hơn đâu' không kích hoạt nhầm multiplier amenity=1.8.
    """
    # 1. Rollback giữ tiện ích tiếng Việt có dấu
    base_pref = UserPreferenceState(max_price=3_000_000.0)
    cur_pref = UserPreferenceState(max_price=4_000_000.0)
    analysis = TurnAnalysis(
        intent="refine_search",
        patch=PreferencePatch(amenities_add=[Amenity.PET_ALLOWED]),
    )
    user_text_clean = strip_accents("quay lại như lúc đầu nhưng thêm thú cưng").lower()

    reverted = _build_revert_preferences(base_pref, analysis, user_text_clean, cur_pref)
    assert Amenity.PET_ALLOWED in reverted.amenities

    # 2. Từ khóa phủ định không kích hoạt nhầm ưu tiên phòng xịn
    negated_text = strip_accents("không cần phòng xịn hơn đâu").lower()
    is_higher = _has_unnegated_keyword(negated_text, ("phong xin hon", "dat hon", "cao hon"))
    assert is_higher is False, "Từ khóa 'phong xin hon' có tiền tố 'khong can' phải bị chặn phủ định"

    unnegated_text = strip_accents("mình muốn tìm phòng xịn hơn").lower()
    assert _has_unnegated_keyword(unnegated_text, ("phong xin hon", "dat hon")) is True


# ==============================================================================
# NHÓM 3: STATE MUTATION & ISOLATION (ADAPTIVE RADIUS SAFE ARGS & SNAPSHOT CAP)
# ==============================================================================

def test_retrieval_node_adaptive_radius_network_failure_preserves_last_args():
    """Nhóm 3: Khi lần mở rộng bán kính Adaptive Radius gặp lỗi mạng, last_search_args['max_distance_km']
    vẫn bảo toàn bán kính thành công trước đó (không bị ghi đè bẩn).
    """
    call_count = 0

    def mock_search_rooms(args):
        nonlocal call_count
        call_count += 1
        rad = args.get("max_distance_km")
        if rad == 2.5:
            # Lần 1 thành công: trả 1 phòng (< 3 phòng -> kích hoạt adaptive expansion)
            return {
                "ok": True,
                "data": [
                    {
                        "id": "r1",
                        "title": "Phòng gần Bách Khoa",
                        "price_vnd": 2_500_000,
                        "lat": 10.8710,
                        "lng": 106.8035,
                    }
                ],
            }
        elif rad == 3.5:
            # Lần 2 gặp lỗi mạng / backend timeout
            return {"ok": False, "error": "Connection timeout khi mở rộng bán kính 3.5km"}
        return {"ok": False, "error": "Unexpected radius"}

    mock_deps = MagicMock()
    mock_session = SessionData("test_retrieval_session")
    mock_deps.sessions.get_or_create_session.return_value = mock_session
    mock_deps.search_rooms = mock_search_rooms
    mock_deps.market_fetcher = None

    retrieval_fn = make_retrieval_node(mock_deps)

    state = {
        "session_id": "test_retrieval_session",
        "preferences": UserPreferenceState(lat=10.8700, lng=106.8031, max_distance_km=None),
        "multipliers": {},
        "computed_weights": {},
        "trace_events": [],
    }

    result = retrieval_fn(state)

    # Xác minh last_search_args bảo toàn bán kính 2.5km thành công, không bị ghi đè bẩn thành 3.5km
    assert result["last_search_args"].get("max_distance_km") == 2.5
    assert len(result["retrieved_rooms"]) == 1


def test_session_data_snapshot_capping_and_initial_preservation():
    """Nhóm 3: SessionData.record_preference_snapshot giới hạn tối đa 20 snapshots
    và bảo toàn 100% snapshot gốc của lượt 1 không bao giờ bị xóa.
    """
    session = SessionData("test_capping_session")

    # Lượt 1: Snapshot ban đầu
    p1 = UserPreferenceState(max_price=2_000_000.0, location_text="Quận 10")
    session.record_preference_snapshot(p1)

    # Ghi tiếp 24 lượt khác nhau (tổng cộng 25 snapshots)
    for i in range(2, 26):
        p_next = UserPreferenceState(max_price=2_000_000.0 + i * 100_000.0, location_text=f"Quận {i}")
        session.record_preference_snapshot(p_next)

    # 1. Kích thước danh sách được chặn trần tối đa 20
    assert len(session.turn_snapshots) == 20

    # 2. Snapshot gốc lượt 1 được bảo toàn tuyệt đối ở vị trí đầu tiên
    assert session.turn_snapshots[0].max_price == 2_000_000.0
    assert session.turn_snapshots[0].location_text == "Quận 10"

    # 3. Snapshot cuối cùng là của lượt gần nhất (lượt 25)
    assert session.turn_snapshots[-1].max_price == 2_000_000.0 + 25 * 100_000.0


# ==============================================================================
# NHÓM 4: PERSISTENCE & RESOURCE CLEANUP (SQLITE CONNECTION CLEAN CLOSING)
# ==============================================================================

def test_persistent_session_store_clean_file_removal_on_windows(tmp_path: Path):
    """Nhóm 4: PersistentSessionStore đóng triệt để mọi sqlite3.Connection trong Generator contextmanager,
    cho phép xóa trực tiếp file SQLite trên Windows mà không bị PermissionError: [WinError 32].
    """
    db_file = tmp_path / "sessions_windows_cleanup_test.db"
    store = PersistentSessionStore(path=db_file)

    # Thực hiện nhiều chu kỳ đọc/ghi
    s1 = store.get_or_create_session("sess_win_01")
    s1.preferences.max_price = 3_500_000.0
    r_item = RoomItem(id="r_win", title="Phòng Windows", price="3.5tr", priceNum=3_500_000.0)
    store.commit_turn(s1, "tìm phòng", "đây là phòng", [r_item], searched=True)

    # Đọc lại từ DB
    s2 = store.get_or_create_session("sess_win_01")
    assert len(s2.history) == 2
    assert len(s2.last_rooms) == 1

    # Thao tác xóa file SQLite trực tiếp ngay trên Windows
    # Nếu còn connection nào chưa đóng (leaked handle), Windows sẽ quăng PermissionError [WinError 32]
    db_file.unlink()
    assert not db_file.exists(), "File database SQLite phải được xóa thành công không bị khóa file descriptor"
