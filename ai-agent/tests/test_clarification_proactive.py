"""Black-box Unit & Integration Tests cho Proactive Search và Ambiguous Landmark Resolution (MỐC 1).

Kiểm thử độc lập theo 4 nhóm test cases:
- Nhóm 1 (Happy Path - Proactive Search): Mốc có cơ sở/quận/ngân sách -> needs_clarification=False -> retrieval_node.
- Nhóm 2 (Ambiguous Path): Mốc đa cơ sở không hint -> kind='ambiguous' -> hỏi lại người dùng.
- Nhóm 3 (Edge Cases): Câu rỗng / danh từ chung -> needs_clarification=True.
- Nhóm 4 (State Consistency & Regression): session.preferences lưu đúng địa danh và ngân sách.
"""

from __future__ import annotations

import pytest

from core.session_store import SessionStore
from domain.schemas import UserPreferenceState
from intelligence.nlu import PreferencePatch, TurnAnalysis
from intelligence.understand import interpret_turn
from tools.housing_tools import geocode_point
from tools.location_service import (
    infer_region_from_location_text,
    resolve_location,
)


class DummyLLM:
    """Mock LLM trả về TurnAnalysis định sẵn cho từng test case."""

    def __init__(self, analysis: TurnAnalysis):
        self._analysis = analysis

    def with_structured_output(self, *args, **kwargs):
        return self

    def invoke(self, *args, **kwargs):
        return self._analysis


class DummyStore:
    def __init__(self):
        self.session = type("DummySession", (), {
            "preferences": UserPreferenceState(),
            "multipliers": {},
            "last_rooms": [],
            "messages": [],
            "history": [],
            "turn_snapshots": [],
            "preference_history": [],
        })()

    def get_or_create_session(self, sid: str):
        return self.session


# =============================================================================
# NHÓM 1: HAPPY PATH - PROACTIVE SEARCH
# =============================================================================


def test_proactive_search_when_location_and_budget_present():
    """Khi có mốc cụ thể và ngân sách, tuyệt đối không hỏi lại."""
    session = DummyStore().get_or_create_session("s1")
    patch = PreferencePatch(location_text="Bách Khoa CS1 Q10", location_kind="place", max_price=4_000_000.0)
    analysis = TurnAnalysis(intent="new_search", patch=patch)
    llm = DummyLLM(analysis)

    plan = interpret_turn("Nữ sinh viên Bách Khoa CS1 Q10 tìm phòng dưới 4 triệu", session, llm)
    assert plan.needs_clarification is False
    assert plan.preferences.max_price == 4_000_000.0
    assert plan.preferences.location_text == "Bách Khoa CS1 Q10"


def test_proactive_search_recovers_from_misflagged_vague_landmark():
    """Tự động giải tỏa cờ mơ hồ sai lệch nếu câu nói đã chứa mốc trường cụ thể."""
    session = DummyStore().get_or_create_session("s2")
    # Giả lập NLU bị ảo giác gán location_is_vague=True cho ĐHQG
    patch = PreferencePatch(location_text="ĐHQG Thủ Đức", location_kind="place", location_is_vague=True, max_price=2_000_000.0)
    analysis = TurnAnalysis(intent="new_search", patch=patch)
    llm = DummyLLM(analysis)

    plan = interpret_turn("Tìm phòng dưới 2 triệu gần ĐHQG Thủ Đức", session, llm)
    assert plan.needs_clarification is False
    assert plan.preferences.location_text == "ĐHQG Thủ Đức"


@pytest.mark.parametrize("loc_text,expected_region", [
    ("Bách Khoa CS1 Q10", "Hồ Chí Minh"),
    ("ĐHQG Thủ Đức", "Hồ Chí Minh"),
    ("SPKT HCMUTE", "Hồ Chí Minh"),
    ("Studio Quận 1", "Hồ Chí Minh"),
    ("Chung cư Q7", "Hồ Chí Minh"),
    ("Gần ĐH Bách Khoa Cầu Giấy", "Hà Nội"),
    ("Khu vực Dĩ An", "Bình Dương"),
])
def test_infer_region_from_abbreviations(loc_text, expected_region):
    """Nhận diện chính xác tỉnh/thành từ từ viết tắt Q1, Q7, Q10, CS1, ĐHQG, SPKT."""
    assert infer_region_from_location_text(loc_text) == expected_region


# =============================================================================
# NHÓM 2: AMBIGUOUS PATH - ĐỊA DANH ĐA CƠ SỞ CHUNG CHUNG
# =============================================================================


def test_ambiguous_landmark_without_hint_returns_candidates():
    """Khi chỉ nói 'Đại học Bách Khoa' trơ trọi mà không có hint -> trả về ambiguous kèm danh sách cơ sở."""
    res = geocode_point("Đại học Bách Khoa", hint=None)
    assert res is not None
    assert res.get("ambiguous") is True
    candidates = res.get("candidates", [])
    assert len(candidates) >= 2
    names = [c["name"] for c in candidates]
    assert any("Hà Nội" in n for n in names)
    assert any("TP.HCM" in n for n in names)


def test_landmark_with_region_hint_is_not_ambiguous():
    """Khi đã có hint='Hồ Chí Minh', mốc 'Đại học Bách Khoa' không bị ambiguous."""
    # Khi có hint, geocode_point bỏ qua bộ lọc ambiguous và gọi request geocode
    # (Trong test không có backend nên có thể trả None hoặc kết quả geocode)
    res = geocode_point("Đại học Bách Khoa CS1 Q10", hint="Hồ Chí Minh")
    # Không phải ambiguous
    assert not (isinstance(res, dict) and res.get("ambiguous") is True)


# =============================================================================
# NHÓM 3: EDGE CASES - CÂU RỖNG VÀ DANH TỪ CHUNG
# =============================================================================


def test_vague_common_noun_triggers_clarification():
    """Danh từ chung không tên riêng ('gần trường đại học') bắt buộc phải hỏi lại."""
    session = DummyStore().get_or_create_session("s3")
    patch = PreferencePatch(location_is_vague=True, vague_category="trường đại học")
    analysis = TurnAnalysis(intent="new_search", patch=patch)
    llm = DummyLLM(analysis)

    plan = interpret_turn("Tìm phòng gần trường đại học", session, llm)
    assert plan.needs_clarification is True
    assert plan.preferences.location_text is None


def test_completely_empty_query_triggers_clarification():
    """Câu nói không có vị trí, không ngân sách, không tiện ích -> hỏi lại."""
    session = DummyStore().get_or_create_session("s4")
    patch = PreferencePatch()
    analysis = TurnAnalysis(intent="smalltalk", patch=patch)
    llm = DummyLLM(analysis)

    plan = interpret_turn("Tìm phòng giúp mình", session, llm)
    assert plan.needs_clarification is True


# =============================================================================
# NHÓM 4: STATE MUTATION & INTEGRATION CONSISTENCY
# =============================================================================


def test_location_and_budget_state_consistency():
    """Đảm bảo preference được lưu giữ trọn vẹn không bị ghi đè rỗng."""
    session = DummyStore().get_or_create_session("s5")
    patch = PreferencePatch(location_text="Bách Khoa Lý Thường Kiệt", location_kind="place", max_price=3_500_000.0)
    analysis = TurnAnalysis(intent="new_search", patch=patch)
    llm = DummyLLM(analysis)

    plan = interpret_turn("Phòng gần Bách Khoa Lý Thường Kiệt tầm 3tr5", session, llm)
    assert plan.preferences.max_price == 3_500_000.0
    assert plan.preferences.location_text == "Bách Khoa Lý Thường Kiệt"
    assert plan.needs_clarification is False
