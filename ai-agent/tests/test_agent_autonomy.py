"""Black-box tests cho tính tự chủ của AI Agent (Mức 1, Mức 2, nhánh 0 phòng tự phân tích & reply).

Bao phủ đủ 4 nhóm kiểm thử theo skill rigorous-testing:
1. Happy Path: NLU tự quyết định trọng số; tìm mới với constrained_generation=False; nhánh 0 phòng nhận dropped_summary & trả reply tự do.
2. Boundary & Edge Cases: câu chứa 'mắc hơn'/'rẻ hơn' không ép trọng số; reply 0 phòng quá ngắn/lỗi fallback về reply_when_no_rooms; bịa số liệu bị verify_node chặn & retry.
3. State Mutation & Isolation: interpret_turn không mutate session gốc; tìm mới không prefetch detail Top 1 hay gán <focus>; dropped_summary không giữ lại sang lượt sau có phòng.
4. Persistence & Config: default_deps() mở constrained_generation=False (override qua env); lưu/nạp session SQLite vẫn giữ đúng multipliers từ NLU.
"""

from __future__ import annotations

import pytest

from domain.budget import _MARKET_CACHE
from domain.schemas import UserPreferenceState
from graph.deps import default_deps
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from intelligence.understand import interpret_turn
from tests.e2e_helpers import FakeAgent, FakeLLM, Harness, agent_reply, nlu, raw_room
from tests.helpers import SKILLS, make_session


@pytest.fixture(autouse=True)
def _clear_market_cache():
    """Đảm bảo không rò rỉ _MARKET_CACHE sang các test khác chạy cùng phiên."""
    _MARKET_CACHE.clear()
    yield
    _MARKET_CACHE.clear()


# ==============================================================================
# NHÓM 1: HAPPY PATH
# ==============================================================================

def test_unconstrained_new_search_uses_free_text_without_forced_top1_focus():
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu("new_search", location_text="UIT", location_kind="place", max_price=3_500_000),
    )
    agent = FakeAgent(
        agent_reply(
            "Mình tìm được 3 phòng gần UIT cho bạn: Top 1 Phòng số 1 giá 2.4 triệu/tháng (25 m²), "
            "Top 2 Phòng số 2 giá 2.8 triệu/tháng (21 m²). Top 1 có mức giá tối ưu nhất."
        )
    )
    rooms = [raw_room(1, 2_400_000, 25), raw_room(2, 2_800_000, 21), raw_room(3, 3_000_000, 30)]
    h = Harness(llm, rooms, agent=agent, constrained_generation=False)

    res = h.turn("tìm phòng gần UIT dưới 3tr5")

    assert len(agent.inputs) == 1
    human_msgs = [m.content for m in agent.inputs[0]["messages"] if getattr(m, "type", "") == "human"]
    assert "<focus>" not in human_msgs[-1]
    assert "<prefetched_listing_detail>" not in human_msgs[0]
    assert "2.4 triệu/tháng" in res.text_reply
    assert res.grounding_report.is_grounded is True


def test_zero_result_receives_dropped_summary_and_allows_free_reply_with_evidence():
    _MARKET_CACHE.clear()
    llm = (
        FakeLLM()
        .on("TurnAnalysis", nlu("new_search", location_text="UIT", location_kind="place", max_price=2_500_000, min_area=20))
        .on(
            "text",
            "Hiện quanh UIT chưa có phòng khớp đủ ngân sách 2.5 triệu/tháng và diện tích từ 20 m². "
            "Thực tế có phòng gần đó giá 3.2 triệu/tháng (25 m²) nhưng đã bị loại vì vượt ngân sách.",
        )
    )
    over_budget_room = raw_room(1, price=3_200_000, area=25)
    h = Harness(llm, [over_budget_room], constrained_generation=False)

    res = h.turn("tìm phòng gần UIT dưới 2tr5, rộng ít nhất 20m2")

    assert res.rooms == []
    assert "3.2 triệu/tháng" in res.text_reply
    assert res.grounding_report.is_grounded is True
    assert res.grounding_report.verifier_output["passed"] is True
    text_calls = [msgs for name, msgs in llm.calls if name == "text"]
    assert len(text_calls) == 1
    human_prompt = text_calls[0][1][1]
    assert "<dropped_rooms>" in human_prompt
    assert "vượt ngân sách" in human_prompt
    assert "Diện tích: 20" in human_prompt


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================

def test_keywords_mac_hon_re_hon_do_not_override_empty_nlu_priorities():
    session = make_session(
        pref=UserPreferenceState(location_text="UIT", max_price=3_500_000),
        multipliers={"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0},
    )
    neutral_llm = FakeLLM().on(
        "TurnAnalysis",
        TurnAnalysis(intent="refine_search", patch=PreferencePatch(), priorities=Priorities()),
    )

    for text in (
        "sao khu này mắc hơn chỗ kia vậy",
        "đắt hơn dự kiến nhưng vẫn tìm quanh đây đi",
        "chỗ kia rẻ hơn nhưng đường hơi tối",
    ):
        plan = interpret_turn(text, session, neutral_llm, skills=SKILLS)
        assert plan.multipliers["amenity"] == 1.0
        assert plan.multipliers["price"] == 1.0


def test_zero_result_hallucinated_amount_is_caught_and_retried_by_verify_node():
    _MARKET_CACHE.clear()
    llm = (
        FakeLLM()
        .on("TurnAnalysis", nlu("new_search", location_text="Dĩ An", location_kind="admin", max_price=2_000_000))
        .on(
            "text",
            "Hiện quanh khu vực này chưa có phòng dưới 2 triệu/tháng, bạn có thể tham khảo mức giá trung bình 9.5 triệu/tháng nhé.",
            "Hiện tại Dĩ An chưa có phòng phù hợp với ngân sách 2 triệu/tháng vì giá sàn khu vực từ 2.5 triệu/tháng.",
        )
    )
    market = lambda **kw: {"minimum_price_vnd": 2_500_000, "average_price_vnd": 3_200_000, "total_listings": 35}
    h = Harness(llm, [], market=market, constrained_generation=False)

    res = h.turn("tìm phòng ở Dĩ An dưới 2 triệu")

    assert res.rooms == []
    assert "9.5 triệu" not in res.text_reply
    assert "2.5 triệu/tháng" in res.text_reply
    assert res.grounding_report.answer_retries == 1
    assert res.grounding_report.is_grounded is True


def test_zero_result_short_or_failed_llm_falls_back_to_deterministic_reply():
    _MARKET_CACHE.clear()
    llm_short = (
        FakeLLM()
        .on("TurnAnalysis", nlu("new_search", location_text="Dĩ An", location_kind="admin", max_price=1_800_000))
        .on("text", "Không có.")
    )
    market = lambda **kw: {"minimum_price_vnd": 2_600_000, "average_price_vnd": 3_300_000, "total_listings": 30}
    h = Harness(llm_short, [], market=market, constrained_generation=False)

    res = h.turn("tìm phòng ở Dĩ An dưới 1tr8")

    assert res.rooms == []
    assert "2.6 triệu/tháng" in res.text_reply
    assert "Homigo hiện chưa tìm thấy" in res.text_reply


def test_unconstrained_new_search_hallucination_triggers_retry_and_passes():
    llm = FakeLLM().on("TurnAnalysis", nlu("new_search", location_text="UIT", location_kind="place", max_price=3_500_000))
    agent = FakeAgent(
        agent_reply("Mình tìm được phòng Top 1 giá chỉ 900k/tháng thôi nhé bạn ơi!"),
        agent_reply("Mình tìm được phòng Top 1 giá 2.4 triệu/tháng (25 m²), khá hợp nhu cầu của bạn."),
    )
    rooms = [raw_room(1, 2_400_000, 25), raw_room(2, 2_800_000, 21)]
    h = Harness(llm, rooms, agent=agent, constrained_generation=False)

    res = h.turn("tìm phòng gần UIT")

    assert len(agent.inputs) == 2
    assert "900k" not in res.text_reply
    assert "2.4 triệu/tháng" in res.text_reply
    assert res.grounding_report.answer_retries == 1
    assert res.grounding_report.is_grounded is True


# ==============================================================================
# NHÓM 3: STATE MUTATION & ISOLATION
# ==============================================================================

def test_interpret_turn_does_not_mutate_session_when_nlu_sets_priorities():
    session = make_session(
        pref=UserPreferenceState(location_text="UIT", max_price=3_000_000),
        multipliers={"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0},
    )
    before_pref = session.preferences.model_dump()
    before_mult = dict(session.multipliers)
    llm = FakeLLM().on(
        "TurnAnalysis",
        TurnAnalysis(intent="refine_search", priorities=Priorities(safety="very_high")),
    )

    plan = interpret_turn("ưu tiên khu an ninh giúp mình", session, llm, skills=SKILLS)

    assert session.preferences.model_dump() == before_pref
    assert session.multipliers == before_mult
    assert plan.multipliers["safety"] == 3.0


def test_dropped_summary_does_not_leak_into_next_turn_with_valid_rooms():
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=2_000_000),
            nlu("refine_search", max_price=3_500_000),
        )
        .on(
            "text",
            "Hiện chưa có phòng dưới 2 triệu/tháng quanh UIT, phòng gần nhất giá 3 triệu/tháng đã bị loại vì vượt ngân sách.",
        )
    )
    agent = FakeAgent(agent_reply("Phòng Top 1 giá 3 triệu/tháng (25 m²) hiện đã phù hợp với ngân sách mới của bạn."))
    room_3m = [raw_room(1, price=3_000_000, area=25)]
    h = Harness(llm, room_3m, agent=agent, constrained_generation=False)

    r1 = h.turn("tìm phòng gần UIT dưới 2 triệu")
    assert r1.rooms == []

    r2 = h.turn("nâng lên 3tr5 đi")
    assert len(r2.rooms) == 1
    assert "3 triệu/tháng" in r2.text_reply
    assert r2.grounding_report.is_grounded is True


# ==============================================================================
# NHÓM 4: PERSISTENCE & DEFAULT CONFIG
# ==============================================================================

def test_default_deps_enables_unconstrained_generation_and_respects_env(monkeypatch):
    monkeypatch.delenv("HOMIGO_CONSTRAINED_GENERATION", raising=False)
    assert default_deps().constrained_generation is False

    monkeypatch.setenv("HOMIGO_CONSTRAINED_GENERATION", "true")
    assert default_deps().constrained_generation is True


def test_nlu_priority_persists_across_sqlite_session_reload(tmp_path):
    from core.session_store import PersistentSessionStore

    db_path = tmp_path / "sessions.db"
    store1 = PersistentSessionStore(path=db_path)
    sess1 = store1.get_or_create_session("persist_weights")

    llm1 = FakeLLM().on(
        "TurnAnalysis",
        TurnAnalysis(
            intent="new_search",
            patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=3_500_000),
            priorities=Priorities(amenity="high"),
            priority_reasons=["ưu tiên tiện nghi tốt trong tầm giá"],
        ),
    )
    plan1 = interpret_turn("tìm phòng Thủ Đức dưới 3tr5 nhiều tiện nghi xịn chút", sess1, llm1, skills=SKILLS)
    sess1.preferences = plan1.preferences
    sess1.multipliers = dict(plan1.multipliers)
    store1.commit_turn(sess1, "tìm phòng Thủ Đức dưới 3tr5 nhiều tiện nghi xịn chút", "ok", [], searched=False)

    store2 = PersistentSessionStore(path=db_path)
    sess2 = store2.get_or_create_session("persist_weights")
    assert sess2.multipliers["amenity"] == 2.0
    assert sess2.preferences.max_price == 3_500_000
