import copy

import pytest

from domain.enums import Amenity, HitlAction, RoomType
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from domain.schemas import UserPreferenceState
from tests.helpers import SKILLS, FakeModel, make_session, room
from intelligence.understand import CUSTOM_TEXT, KEEP_TEXT, interpret_turn, route_after_understand


def run(analysis, session=None, text="câu bất kỳ", **kw):
    session = session or make_session()
    return interpret_turn(text, session, FakeModel(analysis), skills=SKILLS, **kw), session


# ---------------- tìm kiếm ----------------
def test_new_search_applies_patch_priorities_and_weights():
    a = TurnAnalysis(intent="new_search", patch=PreferencePatch(location_text="UIT", max_price=3_500_000, preferred_amenities_add=["ml"]),
                     priorities=Priorities(price="high"), priority_reasons=["ưu tiên giá rẻ"])
    plan, _ = run(a)
    assert plan.preferences.location_text == "UIT" and plan.preferences.max_price == 3_500_000
    assert plan.preferences.preferred_amenities == [Amenity.AIRCON]
    assert plan.multipliers["price"] == 2.0 and plan.weight_explanations == ["ưu tiên giá rẻ"]
    assert not plan.needs_clarification and plan.commit and not plan.used_fallback
    assert "amenity" in plan.computed_weights and "location" not in plan.computed_weights    # chưa có toạ độ
    assert abs(sum(plan.computed_weights.values()) - 1.0) < 1e-9


def test_interpret_is_pure_session_untouched():
    s = make_session(pref=UserPreferenceState(max_price=3e6, amenities=["ml"]))
    before = (s.preferences.model_dump(), dict(s.multipliers))
    plan, _ = run(TurnAnalysis(intent="refine_search", patch=PreferencePatch(max_price=4e6, amenities_add=["camera"]),
                               priorities=Priorities(price="very_high")), s)
    assert (s.preferences.model_dump(), s.multipliers) == before
    assert plan.preferences.max_price == 4e6 and plan.multipliers["price"] == 3.0


def test_priority_persists_across_turns_and_reset():
    s = make_session(multipliers={"price": 2.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0}, messages=["x"])
    plan, _ = run(TurnAnalysis(intent="refine_search", patch=PreferencePatch(max_price=4e6)), s)
    assert plan.multipliers["price"] == 2.0                                      # không nhắc -> giữ
    plan, _ = run(TurnAnalysis(intent="new_search", reset_priorities=True, patch=PreferencePatch(location_text="Q7")), s)
    assert plan.multipliers["price"] == 1.0                                      # nhu cầu mới -> đặt lại
    plan, _ = run(TurnAnalysis(intent="refine_search", priorities=Priorities(price="lower")), s)
    assert plan.multipliers["price"] == 0.5                                      # hạ được (bản cũ không làm được)


def test_vague_location_needs_clarification_and_not_written():
    a = TurnAnalysis(intent="new_search", patch=PreferencePatch(location_is_vague=True, vague_category="khu công nghiệp", location_region="Bình Dương"))
    plan, _ = run(a)
    assert plan.needs_clarification and plan.preferences.location_text is None
    assert plan.vague_location_info == {"category": "khu công nghiệp", "region": "Bình Dương"}


def test_needs_clarification_rules():
    plan, _ = run(TurnAnalysis(intent="new_search"))                              # chưa có gì, chưa có lịch sử
    assert plan.needs_clarification
    plan, _ = run(TurnAnalysis(intent="new_search"), make_session(messages=["đã chat"]))
    assert not plan.needs_clarification                                           # có lịch sử -> không hỏi lại
    plan, _ = run(TurnAnalysis(intent="new_search", patch=PreferencePatch(max_price=3e6)))
    assert not plan.needs_clarification


def test_room_type_exclusion_flows_into_preferences():
    plan, _ = run(TurnAnalysis(intent="refine_search", patch=PreferencePatch(room_types_exclude=["ktx"])), make_session(pref=UserPreferenceState(room_type="ktx"), messages=["x"]))
    assert plan.preferences.room_type is None and plan.preferences.excluded_room_types == [RoomType.SLEEPBOX]


# ---------------- HITL ----------------
def _hitl(act, session=None, patch=None, **kw):
    s = session or make_session(pref=UserPreferenceState(max_price=3_000_000, amenities=["ml"], location_text="Q1", ward_id=7, district_id=1, city_id=79),
                                hitl_streak=1, proposed_budget=3_450_000)
    return run(TurnAnalysis(intent="hitl_choice", hitl_action=act, patch=patch or PreferencePatch()), s, **kw)


def test_hitl_keep():
    plan, _ = _hitl(HitlAction.KEEP)
    assert plan.is_keep and plan.direct_reply and plan.final_text == KEEP_TEXT and not plan.commit
    assert route_after_understand({"is_keep_criteria": True, "direct_reply": True}) == "formatter_node"


def test_hitl_custom_click_vs_text():
    plan, _ = _hitl(HitlAction.CUSTOM, ui_action="custom")           # bấm nút -> trả lời sẵn, không qua LLM clarification
    assert plan.direct_reply and plan.needs_clarification and plan.final_text == CUSTOM_TEXT
    plan, _ = _hitl(HitlAction.CUSTOM, patch=PreferencePatch(max_price=5e6))   # gõ tiêu chí mới -> tìm lại
    assert not plan.direct_reply and plan.preferences.max_price == 5e6 and plan.commit


def test_hitl_relax_budget_uses_proposed_then_default_then_patch():
    plan, _ = _hitl(HitlAction.RELAX_BUDGET)
    assert plan.preferences.max_price == 3_450_000 and plan.multipliers["price"] == 1.5 and plan.weight_explanations
    s = make_session(pref=UserPreferenceState(max_price=4_000_000), hitl_streak=1)
    plan, _ = _hitl(HitlAction.RELAX_BUDGET, session=s)
    assert plan.preferences.max_price == 4_600_000                   # +15% khi không có mức đề xuất
    s = make_session(hitl_streak=1)
    plan, _ = _hitl(HitlAction.RELAX_BUDGET, session=s)
    assert plan.preferences.max_price == 3_450_000                   # mặc định 3tr * 1.15
    plan, _ = _hitl(HitlAction.RELAX_BUDGET, patch=PreferencePatch(max_price=3_800_000))
    assert plan.preferences.max_price == 3_800_000                   # người dùng tự nêu số thì thắng


def test_hitl_dormitory_overrides_exclusion():
    s = make_session(pref=UserPreferenceState(excluded_room_types=["ktx"]), hitl_streak=1)
    plan, _ = _hitl(HitlAction.DORMITORY, session=s)
    assert plan.preferences.room_type is RoomType.SLEEPBOX and plan.preferences.excluded_room_types == []
    assert plan.multipliers["price"] == 1.8


def test_hitl_reduce_amenities_and_broaden_ladder():
    plan, _ = _hitl(HitlAction.REDUCE_AMENITIES)
    assert plan.preferences.amenities == [] and "amenity" not in plan.computed_weights
    s = make_session(pref=UserPreferenceState(location_text="Q1", ward_id=7, district_id=1, city_id=79), hitl_streak=1)
    p1, _ = _hitl(HitlAction.BROADEN, session=s)
    assert p1.preferences.ward_id is None and p1.preferences.district_id == 1
    s.preferences = p1.preferences
    p2, _ = _hitl(HitlAction.BROADEN, session=s)
    assert p2.preferences.district_id is None and p2.preferences.city_id == 79
    s.preferences = p2.preferences
    p3, _ = _hitl(HitlAction.BROADEN, session=s)
    assert p3.preferences.city_id is None and p3.preferences.location_text is None     # cuối cùng xoá hẳn vị trí
    assert not p3.needs_clarification                                                  # đang trong HITL -> không hỏi lại


def test_ui_action_bypasses_model_and_accepts_strings():
    m = FakeModel(RuntimeError("không được gọi"))
    s = make_session(hitl_streak=1, proposed_budget=3_000_000)
    plan = interpret_turn("👍 whatever", s, m, ui_action="relax_budget", skills=SKILLS)
    assert plan.preferences.max_price == 3_000_000 and m.structured.calls == []
    plan = interpret_turn("x", s, m, ui_action="không_tồn_tại", skills=SKILLS)           # rác -> bỏ qua, chạy đường LLM (lỗi -> fallback)
    assert plan.used_fallback


# ---------------- các intent khác ----------------
def test_followup_returns_flag_rank_and_route():
    s = make_session(rooms=[room(1), room(2)])
    plan, _ = run(TurnAnalysis(intent="room_followup", referenced_room_rank=2), s)
    assert plan.is_followup and plan.focus_rank == 2 and not plan.commit
    assert route_after_understand({"is_followup": True}) == "decision_node"


def test_followup_without_rooms_becomes_search():
    plan, _ = run(TurnAnalysis(intent="room_followup", referenced_room_rank=1))
    assert not plan.is_followup and plan.intent == "new_search"


def test_skill_advice_routes_to_advisory():
    plan, _ = run(TurnAnalysis(intent="skill_advice", skill_slug="rental-contract-advisor"))
    assert plan.matched_skill == "rental-contract-advisor" and not plan.commit and not plan.needs_clarification
    assert route_after_understand({"matched_skill": "x"}) == "advisory_node"


@pytest.mark.parametrize("intent,reason", [("prompt_injection", "PROMPT_INJECTION_DETECTED"), ("off_topic", "OFF_TOPIC_QUERY")])
def test_blocked_intents(intent, reason):
    plan, _ = run(TurnAnalysis(intent=intent))
    assert plan.blocked_reason == reason and plan.final_text and not plan.commit and not plan.needs_clarification


def test_smalltalk_goes_to_clarification_llm():
    plan, _ = run(TurnAnalysis(intent="smalltalk"))
    assert plan.needs_clarification and not plan.direct_reply
    assert route_after_understand({"needs_clarification": True}) == "clarification_node"


def test_route_priority_and_default():
    class G:  # guardrail bị chặn
        allowed = False
    assert route_after_understand({"guardrail_result": G(), "matched_skill": "x"}) == "formatter_node"
    assert route_after_understand({"is_followup": True, "matched_skill": "x", "needs_clarification": True}) == "decision_node"
    assert route_after_understand({}) == "retrieval_node"
    assert route_after_understand({"direct_reply": True, "needs_clarification": True}) == "formatter_node"


# ---------------- fallback khi LLM lỗi ----------------
def test_llm_failure_uses_fallback_and_flags_it():
    s = make_session(pref=UserPreferenceState(max_price=3e6), hitl_streak=1, proposed_budget=3_450_000)
    plan = interpret_turn("❌ Giữ nguyên tiêu chí của tôi", s, FakeModel(RuntimeError("down")), skills=SKILLS)
    assert plan.used_fallback and plan.is_keep
    plan = interpret_turn("tìm phòng giá rẻ", make_session(), None, skills=SKILLS)           # không có model
    assert plan.used_fallback and plan.multipliers["price"] == 2.0 and plan.needs_clarification
    plan = interpret_turn("gần khu công nghiệp ở Bình Dương", make_session(), None, skills=SKILLS)
    assert plan.vague_location_info == {"category": "khu công nghiệp", "region": "binh duong"} and plan.needs_clarification
