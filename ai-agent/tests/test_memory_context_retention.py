"""Kiểm thử chuyên sâu chống mất ngữ cảnh (Memory & Context Retention).

Kiểm chứng các trường hợp:
1. Chặn LLM tự ý clear location ('UIT') khi người dùng chỉ nói thêm tiện ích (vd: 'thêm máy lạnh').
2. Chặn LLM tự ý clear price, area, room_type, amenities, special_requirements.
3. Điều chỉnh ngân sách 2 chiều: 'rẻ hơn nữa' (-15%) và 'đắt hơn/phòng xịn hơn' (+15%).
4. Duy trì focused_room_rank qua các lượt hỏi followup liên tiếp (hỏi phòng 2 -> lượt sau hỏi tiếp tiền cọc vẫn là phòng 2).
5. Nén hội thoại 2 chiều (compact_history_tuples) cung cấp đúng ngữ cảnh cho NLU.
"""

import pytest

from core.session_store import SessionData, SessionStore
from domain.enums import Amenity, RoomType
from domain.schemas import RoomItem, UserPreferenceState
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis, _postprocess
from intelligence.understand import interpret_turn
from tests.e2e_helpers import FakeLLM, nlu
from tests.helpers import room


def test_clear_guardrail_prevents_accidental_location_deletion():
    """Kiểm tra Guardrail trong _postprocess chặn LLM tự tiện xóa location khi người dùng chỉ nói 'thêm máy lạnh'."""
    # Giả lập LLM tự tiện sinh clear: ['location', 'price', 'amenities']
    analysis = TurnAnalysis(
        intent="refine_search",
        patch=PreferencePatch(
            amenities_add=[Amenity.AIRCON],
            clear=["location", "price", "amenities"],
        ),
    )

    # 1. Người dùng chỉ nói "thêm máy lạnh nữa nha" -> Bác bỏ clear location, price, amenities
    processed = _postprocess(analysis.model_copy(deep=True), user_text="thêm máy lạnh nữa nha")
    assert "location" not in processed.patch.clear
    assert "price" not in processed.patch.clear
    assert "amenities" not in processed.patch.clear
    assert processed.patch.amenities_add == [Amenity.AIRCON]

    # 2. Người dùng chủ động nói "bỏ vị trí cũ đi, tìm ở đâu cũng được" -> Cho phép clear location
    analysis_loc = analysis.model_copy(deep=True)
    processed_loc = _postprocess(analysis_loc, user_text="bỏ vị trí cũ đi, tìm ở đâu cũng được")
    assert "location" in processed_loc.patch.clear

    # 3. Người dùng nói "reset hết yêu cầu" -> Cho phép clear toàn bộ
    analysis_reset = analysis.model_copy(deep=True)
    processed_reset = _postprocess(analysis_reset, user_text="reset lại từ đầu tìm phòng mới")
    assert "location" in processed_reset.patch.clear
    assert "price" in processed_reset.patch.clear


def test_clear_guardrail_protects_all_six_groups():
    """Kiểm tra Guardrail bảo vệ toàn bộ 6 nhóm tiêu chí tích lũy."""
    analysis = TurnAnalysis(
        intent="refine_search",
        patch=PreferencePatch(
            clear=["location", "price", "area", "room_type", "amenities", "special_requirements"],
        ),
    )
    # Câu nói bình thường không có từ khóa hủy -> Bác bỏ toàn bộ clear
    processed = _postprocess(analysis.model_copy(deep=True), user_text="cho mình xem thêm phòng có gác")
    assert processed.patch.clear == []


def test_budget_adjustment_two_way_cheaper_and_higher():
    """Kiểm tra điều chỉnh ngân sách 2 chiều: 'rẻ hơn' (-15%) và 'đắt hơn/phòng xịn hơn' (+15%)."""
    session = SessionData("test_budget_adj")
    session.preferences = UserPreferenceState(location_text="UIT", max_price=4_000_000.0)

    # 1. Người dùng nói "rẻ hơn nữa nha" -> Giảm trần ngân sách 15% (4tr -> 3.4tr)
    fake_model = FakeLLM().on(
        TurnAnalysis,
        TurnAnalysis(
            intent="refine_search",
            patch=PreferencePatch(),
            priorities=Priorities(),
        ),
    )
    plan_cheaper = interpret_turn("tìm phòng rẻ hơn nữa nha", session, fake_model)
    assert plan_cheaper.preferences.max_price == 3_400_000.0
    assert plan_cheaper.multipliers.get("price") == 2.0

    # 2. Người dùng nói "đắt hơn chút cũng được, phòng xịn hơn" -> Tăng trần ngân sách 15% (3.4tr -> 3.9tr)
    session.preferences.max_price = 3_400_000.0
    plan_higher = interpret_turn("nới giá lên xíu phòng xịn hơn cũng được", session, fake_model)
    assert plan_higher.preferences.max_price == 3_900_000.0
    assert plan_higher.multipliers.get("amenity") == 1.8


def test_session_focus_rank_retention_and_persistence(tmp_path):
    """Kiểm tra focused_room_rank được duy trì qua các lượt và lưu bền vào SQLite."""
    from core.session_store import PersistentSessionStore

    db_path = tmp_path / "sessions.db"
    store = PersistentSessionStore(path=db_path)
    sess = store.get_or_create_session("focus_sess")

    # Giả lập lượt 1 đề xuất 3 phòng
    r1, r2, r3 = room(1), room(2), room(3)
    store.commit_turn(sess, "tìm phòng", "đây là các phòng", [r1, r2, r3], searched=True)
    assert sess.focused_room_rank is None

    # Lượt 2: Người dùng hỏi phòng 2 -> set focused_room_rank = 2
    sess.focused_room_rank = 2
    store.commit_turn(sess, "phòng số 2 có ban công không", "phòng 2 có ban công", [], searched=False)

    # Khởi động lại store mới từ file DB -> focused_room_rank phải còn nguyên = 2
    store2 = PersistentSessionStore(path=db_path)
    sess2 = store2.get_or_create_session("focus_sess")
    assert sess2.focused_room_rank == 2

    # Lượt 3: Người dùng hỏi "tiền cọc mấy tháng" (không nhắc lại số 2) -> interpret_turn phải kế thừa rank 2
    fake_model = FakeLLM().on(
        TurnAnalysis,
        TurnAnalysis(
            intent="room_followup",
            referenced_room_rank=None,  # LLM không bắt được số vì user không nói
        ),
    )
    plan = interpret_turn("tiền cọc ở đây mấy tháng vậy anh?", sess2, fake_model)
    assert plan.is_followup is True
    assert plan.focus_rank == 2  # Kế thừa đúng phòng số 2!


def test_compact_history_tuples():
    """Kiểm tra compact_history_tuples rút gọn đúng lời thoại trợ lý và giữ nguyên user."""
    s = SessionData("test_compact")
    s.history = [
        ("user", "Tìm phòng gần UIT dưới 3tr"),
        (
            "assistant",
            "Homigo đã tìm được 5 phòng phù hợp:\n### 1. Phòng trọ A\n- Giá: 2.5tr\n### 2. Phòng trọ B\n- Giá: 2.8tr",
        ),
        ("user", "Thêm máy lạnh nữa nha"),
    ]
    tuples = s.compact_history_tuples(window=4)
    assert len(tuples) == 3
    assert tuples[0] == ("user", "Tìm phòng gần UIT dưới 3tr")
    assert "[Đã gợi ý danh sách phòng]" in tuples[1][1]
    assert tuples[2] == ("user", "Thêm máy lạnh nữa nha")
