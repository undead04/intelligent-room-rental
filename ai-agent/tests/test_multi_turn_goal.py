"""Kiểm thử Chống Trôi Mục Tiêu Đa Lượt (Anti-Goal-Drift) & Tổng Hợp Truy Vấn RAG.

Kiểm chứng các kịch bản:
1. Quay lại mốc tìm kiếm trước đó (Rollback & Memory)
2. Loại bỏ Zombie Constraints (Dọn dẹp tiêu chí mềm cũ bằng special_requirements_remove & clear)
3. Tổng hợp câu RAG thuần khiết từ UserPreferenceState (Không còn từ đệm giao tiếp)
4. Lưu và khôi phục Preference Snapshots trong SessionStore
5. Contextual Query Rewriting qua semantic_query của LLM (Kiến trúc Dual-Layer)
"""

import pytest

from domain.enums import Amenity, RoomType
from domain.schemas import RoomItem, UserPreferenceState
from graph.nodes.retrieval import build_query, synthesize_structured_query
from intelligence.advice import Advice
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis, apply_patch
from core.session_store import PersistentSessionStore, SessionData
from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, Harness, nlu, raw_room


def test_special_requirements_removal_and_clearing():
    """Kiểm tra apply_patch hỗ trợ xoá yêu cầu mềm và clear nhóm special_requirements."""
    p0 = UserPreferenceState(
        location_text="Bình Thạnh",
        special_requirements=["view Landmark", "gần bờ kè", "hẻm xe hơi"],
    )

    # 1. Xoá từng yêu cầu mềm qua special_requirements_remove
    patch_remove = PreferencePatch(
        special_requirements_remove=["gần bờ kè"],
    )
    p1 = apply_patch(p0, patch_remove)
    assert p1.special_requirements == ["view Landmark", "hẻm xe hơi"]

    # 2. Xoá toàn bộ special_requirements qua clear
    patch_clear = PreferencePatch(clear=["special_requirements"])
    p2 = apply_patch(p1, patch_clear)
    assert p2.special_requirements == []


def test_preference_history_snapshot_retention():
    """Kiểm tra SessionData lưu tối đa 5 snapshot khác nhau và bỏ qua snapshot trùng."""
    s = SessionData("test_snap_sess")
    assert len(s.preference_history) == 0

    # Snapshot 1
    pref1 = UserPreferenceState(location_text="Bình Thạnh", max_price=4_000_000)
    s.record_preference_snapshot(pref1)
    assert len(s.preference_history) == 1

    # Trùng snapshot 1 -> không lưu thừa
    s.record_preference_snapshot(pref1)
    assert len(s.preference_history) == 1

    # Thêm 5 snapshot tiếp theo (tổng 6 cái khác nhau)
    for i in range(2, 7):
        p = UserPreferenceState(location_text=f"Quận {i}", max_price=i * 1_000_000)
        s.record_preference_snapshot(p)

    # Chỉ giữ tối đa 5 snapshots gần nhất
    assert len(s.preference_history) == 5
    assert s.preference_history[-1].location_text == "Quận 6"
    assert s.preference_history[0].location_text == "Quận 2"


def test_preference_history_persistence(tmp_path):
    """Kiểm tra preference_history sống qua restart trong PersistentSessionStore (SQLite)."""
    db_file = tmp_path / "sessions.db"
    store1 = PersistentSessionStore(path=db_file)
    sess1 = store1.get_or_create_session("persisted_sess")

    p = UserPreferenceState(location_text="Thủ Đức", max_price=3_500_000)
    sess1.preferences = p
    sess1.record_preference_snapshot(p)
    store1.commit_turn(sess1, "Tìm phòng Thủ Đức", "Đã tìm thấy phòng", [])

    # Khởi động lại store mới từ cùng file DB
    store2 = PersistentSessionStore(path=db_file)
    sess2 = store2.get_or_create_session("persisted_sess")
    assert len(sess2.preference_history) == 1
    assert sess2.preference_history[0].location_text == "Thủ Đức"
    assert sess2.preference_history[0].max_price == 3_500_000


def test_build_query_pure_synthesis():
    """Kiểm tra build_query loại bỏ 100% từ đệm hội thoại/than phiền/quay xe."""
    pref = UserPreferenceState(
        room_type=RoomType.ROOM,
        location_text="Bình Thạnh",
        amenities=[Amenity.MEZZANINE, Amenity.PET_ALLOWED],
        preferred_amenities=[Amenity.AIRCON],
        special_requirements=["gần bờ kè"],
    )

    user_chatters = [
        "Thôi nghe phức tạp quá, bây giờ quay lại tìm phòng trọ ở Bình Thạnh dưới 4 triệu có gác lúc nãy đi, nhưng đổi ý là phải được nuôi pet nha",
        "Bạn ơi có chỗ nào như nãy không giúp mình với ạ?",
        "Kiếm giùm em phòng nào rẻ rẻ xíu đi",
    ]

    for chatter in user_chatters:
        q = build_query(pref, user_text=chatter)
        assert "Thôi nghe phức tạp quá" not in q
        assert "bây giờ quay lại" not in q
        assert "giúp mình với" not in q
        assert "khu vực Bình Thạnh" in q
        assert "gác lửng" in q
        assert "cho nuôi pet" in q
        assert "ưu tiên máy lạnh" in q
        assert "gần bờ kè" in q


def test_contextual_query_rewriting_precedence():
    """Kiểm tra Dual-Layer: Lớp 1 (semantic_query do LLM viết lại) được ưu tiên hàng đầu."""
    pref = UserPreferenceState(
        room_type=RoomType.ROOM,
        location_text="UIT",
        amenities=[Amenity.AIRCON, Amenity.MEZZANINE],
    )

    # Khi có semantic_query tự nhiên từ LLM
    q = build_query(
        pref,
        user_text="Tìm phòng gần UIT dưới 5 triệu có máy lạnh, gác lửng, giờ giấc tự do",
        semantic_query="Phòng trọ gần UIT có máy lạnh, gác lửng, giờ giấc tự do",
    )
    assert q == "Phòng trọ gần UIT có máy lạnh, gác lửng, giờ giấc tự do"

    # Khi semantic_query rỗng -> tự động fallback sang Lớp 2 (tổng hợp từ State)
    q_fallback = build_query(
        pref,
        user_text="Thôi dẹp đi",
        semantic_query="",
    )
    assert "khu vực UIT" in q_fallback
    assert "máy lạnh" in q_fallback
    assert "gác lửng" in q_fallback


def test_multi_turn_goal_retention_end_to_end():
    """Kịch bản E2E kiểm tra quay lại mục tiêu ban đầu sau nhiều lượt chat:
    - Lượt 1: Tìm phòng Thủ Đức dưới 4tr có gác, gần bờ kè (sử dụng semantic_query từ LLM)
    - Lượt 2: Thử đổi sang Quận 7 dưới 5tr có ban công
    - Lượt 3: Quay lại tìm như lúc đầu ở Thủ Đức, thêm cho nuôi pet
    """
    t1 = nlu(
        "new_search",
        location_text="Thủ Đức",
        location_kind="admin",
        max_price=4_000_000,
        amenities_add=["mezzanine"],
        special_requirements_add=["gần bờ kè"],
        semantic_query="Phòng trọ tại Thủ Đức có gác lửng, gần bờ kè",
    )
    t2 = nlu(
        "new_search",
        location_text="Quận 7",
        location_kind="admin",
        max_price=5_000_000,
        amenities_add=["window_balcony"],
        clear=["amenities", "special_requirements"],
        semantic_query="Phòng trọ tại Quận 7 có ban công hoặc cửa sổ thoáng",
    )
    t3 = nlu(
        "new_search",
        location_text="Thủ Đức",
        location_kind="admin",
        max_price=4_000_000,
        amenities_add=["mezzanine", "pet_allowed"],
        special_requirements_add=["gần bờ kè"],
        clear=["amenities"],
        semantic_query="Phòng trọ tại Thủ Đức có gác lửng, cho nuôi pet, gần bờ kè",
    )

    llm = FakeLLM()
    llm.on(TurnAnalysis, t1, t2, t3)
    llm.on(Advice, GOOD_ADVICE)

    h = Harness(llm, rooms=[raw_room(1, price=3_800_000)])
    sid = "multi_turn_retention_sess"

    # Lượt 1: Thủ Đức
    h.turn("Tìm phòng trọ ở Thủ Đức dưới 4 triệu có gác lửng, gần bờ kè", session_id=sid)
    s1 = h.sessions.get_or_create_session(sid)
    assert s1.preferences.location_text == "Thủ Đức"
    assert s1.preferences.max_price == 4_000_000
    assert Amenity.MEZZANINE in s1.preferences.amenities
    assert "gần bờ kè" in s1.preferences.special_requirements
    q1 = h.search_calls[0]["query"]
    assert q1 == "Phòng trọ tại Thủ Đức có gác lửng, gần bờ kè"

    # Lượt 2: Quận 7 (Dọn dẹp gác lửng và gần bờ kè của Thủ Đức)
    h.turn("Thử xem bên Quận 7 dưới 5 triệu có ban công xem sao", session_id=sid)
    s2 = h.sessions.get_or_create_session(sid)
    assert s2.preferences.location_text == "Quận 7"
    assert s2.preferences.max_price == 5_000_000
    assert s2.preferences.amenities == [Amenity.WINDOW_BALCONY]
    assert s2.preferences.special_requirements == []  # Không còn zombie requirement
    q2 = h.search_calls[1]["query"]
    assert q2 == "Phòng trọ tại Quận 7 có ban công hoặc cửa sổ thoáng"

    # Lượt 3: Quay lại Thủ Đức như lúc đầu + thêm nuôi pet
    h.turn(
        "Thôi bên đó đắt quá, quay lại tìm như lúc đầu ở Thủ Đức đi nhưng thêm điều kiện cho nuôi pet nha",
        session_id=sid,
    )
    s3 = h.sessions.get_or_create_session(sid)
    assert s3.preferences.location_text == "Thủ Đức"
    assert s3.preferences.max_price == 4_000_000
    assert Amenity.MEZZANINE in s3.preferences.amenities
    assert Amenity.PET_ALLOWED in s3.preferences.amenities
    assert "gần bờ kè" in s3.preferences.special_requirements
    assert len(s3.preference_history) >= 2

    # Kiểm tra câu RAG gửi vào Backend vector-search
    q3 = h.search_calls[2]["query"]
    assert q3 == "Phòng trọ tại Thủ Đức có gác lửng, cho nuôi pet, gần bờ kè"
    assert "Thôi bên đó đắt quá" not in q3
    assert "quay lại tìm như lúc đầu" not in q3
