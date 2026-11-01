import pytest

from domain.enums import Amenity, RoomType
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from domain.schemas import UserPreferenceState
from tests.helpers import SKILLS, FakeModel, make_session, room
from intelligence.understand import interpret_turn, route_after_understand


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
    assert not plan.needs_clarification and plan.commit
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
    assert plan.multipliers["price"] == 0.5                                      # hạ được


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


# ---------------- các intent khác ----------------
def test_followup_returns_flag_rank_and_route():
    s = make_session(rooms=[room(1), room(2)])
    plan, _ = run(TurnAnalysis(intent="room_followup", referenced_room_rank=2), s)
    assert plan.is_followup and plan.focus_rank == 2 and not plan.commit
    assert route_after_understand({"is_followup": True}) == "decision_node"


def test_followup_without_rooms_routes_to_clarification():
    plan, _ = run(TurnAnalysis(intent="room_followup", referenced_room_rank=1))
    assert not plan.is_followup and plan.intent == "room_followup" and plan.needs_clarification
    assert route_after_understand({"needs_clarification": plan.needs_clarification}) == "clarification_node"


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


# ---------------- khi LLM lỗi hoặc không có model ----------------
def test_llm_failure_or_none_model_routes_to_clarification():
    s = make_session(pref=UserPreferenceState(max_price=3e6))
    plan = interpret_turn("tìm phòng giá rẻ", s, FakeModel(RuntimeError("down")), skills=SKILLS)
    assert plan.needs_clarification and not plan.commit
    plan2 = interpret_turn("tìm phòng giá rẻ", make_session(), None, skills=SKILLS)
    assert plan2.needs_clarification and not plan2.commit


def test_multi_intent_saves_patch_and_returns_natural_chat_without_buttons():
    a = TurnAnalysis(
        intent="new_search",
        skill_slug="rental-contract-advisor",
        patch=PreferencePatch(location_text="UIT", max_price=3_500_000, amenities_add=["aircon"]),
        priorities=Priorities(price="high"),
    )
    plan, _ = run(a)
    assert plan.commit is True
    assert plan.preferences.location_text == "UIT" and plan.preferences.max_price == 3_500_000
    assert plan.preferences.amenities == [Amenity.AIRCON]
    assert plan.multipliers["price"] == 2.0
    assert plan.direct_reply is True and plan.needs_clarification is True
    assert "ghi nhận sẵn các tiêu chí tìm phòng" in plan.final_text
    assert "tư vấn về tư vấn hợp đồng thuê trọ, tiền cọc trước" in plan.final_text
    assert route_after_understand({"direct_reply": plan.direct_reply, "needs_clarification": plan.needs_clarification}) == "formatter_node"
