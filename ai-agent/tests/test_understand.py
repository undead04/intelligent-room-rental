import pytest

from domain.enums import Amenity, RoomType
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from domain.schemas import UserPreferenceState
from tests.helpers import SKILLS, FakeModel, make_session, room
from graph.routing import route_after_understand
from intelligence.understand import interpret_turn


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
    plan, _ = run(TurnAnalysis(intent="new_search"))                              # chưa có location -> hỏi làm rõ
    assert plan.needs_clarification
    plan, _ = run(TurnAnalysis(intent="new_search"), make_session(messages=["đã chat"]))
    assert plan.needs_clarification                                               # có lịch sử nhưng vẫn thiếu location -> hỏi làm rõ
    plan, _ = run(TurnAnalysis(intent="new_search"), make_session(pref=UserPreferenceState(location_text="UIT"), messages=["đã chat"]))
    assert not plan.needs_clarification                                           # đã có location trong session -> cho tìm
    plan, _ = run(TurnAnalysis(intent="new_search", patch=PreferencePatch(max_price=3e6)))
    assert plan.needs_clarification and plan.commit and plan.preferences.max_price == 3_000_000  # thiếu location -> lưu giá + hỏi khu vực
    plan, _ = run(TurnAnalysis(intent="new_search", patch=PreferencePatch(location_text="UIT")))
    assert not plan.needs_clarification                                           # có location (dù chưa có giá) -> cho tìm


def test_room_type_exclusion_flows_into_preferences():
    plan, _ = run(TurnAnalysis(intent="refine_search", patch=PreferencePatch(excluded_room_types=["ktx"])), make_session(pref=UserPreferenceState(allowed_room_types=["ktx"]), messages=["x"]))
    assert plan.preferences.allowed_room_types == [] and plan.preferences.excluded_room_types == [RoomType.SLEEPBOX]


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


def test_multi_intent_plans_sequential_tasks_and_saves_patch():
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
    assert plan.direct_reply is False and plan.needs_clarification is False
    assert plan.current_task == "search"
    assert plan.pending_tasks == ["advisory"]
    assert plan.matched_skill == "rental-contract-advisor"
    assert route_after_understand({"current_task": plan.current_task, "matched_skill": plan.matched_skill}) == "retrieval_node"


def test_concrete_poi_rescued_when_nlu_marks_location_is_vague():
    """Nếu NLU đánh nhầm địa danh cụ thể trong POI dict (vd KCN Amata Biên Hòa) là location_is_vague -> giải cứu sang retrieval."""
    a = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text="KCN Amata Biên Hòa",
            location_kind="place",
            location_is_vague=True,
            vague_category="khu công nghiệp",
            location_region="Đồng Nai",
        ),
    )
    plan, _ = run(a)
    assert plan.needs_clarification is False
    assert plan.preferences.location_text == "KCN Amata Biên Hòa"
    assert route_after_understand({"needs_clarification": plan.needs_clarification}) == "retrieval_node"


def test_concrete_poi_rescued_from_user_text_when_nlu_omits_location_text():
    """Khi LLM đặt location_text=None + location_is_vague=True dù user nêu tên riêng KCN Amata Biên Hòa -> vẫn giải cứu; câu mơ hồ thực sự giữ nguyên clarify."""
    a_concrete = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text=None,
            location_is_vague=True,
            vague_category="khu công nghiệp",
            location_region="Đồng Nai",
        ),
    )
    plan_ok, _ = run(a_concrete, text="Tìm trọ gần KCN Amata Biên Hòa")
    assert plan_ok.needs_clarification is False
    assert plan_ok.preferences.location_text == "KCN Amata Biên Hòa"
    assert route_after_understand({"needs_clarification": plan_ok.needs_clarification}) == "retrieval_node"

    # Trường hợp mơ hồ thật sự ("gần khu công nghiệp ở Bình Dương") -> PHẢI tiếp tục clarify
    a_vague = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text=None,
            location_is_vague=True,
            vague_category="khu công nghiệp",
            location_region="Bình Dương",
        ),
    )
    plan_vague, _ = run(a_vague, text="Tìm trọ gần khu công nghiệp ở Bình Dương")
    assert plan_vague.needs_clarification is True
    assert plan_vague.preferences.location_text is None


def test_pending_ambiguous_candidate_selection_resolves_directly_without_loop():
    """Chọn ứng viên theo STT hoặc tên chip từ pending_ambiguous_candidates -> gán thẳng tọa độ, không hỏi vòng lặp."""
    cands = [
        {"name": "ĐH Bách Khoa - Cơ sở 1 (Quận 10)", "lat": 10.7726, "lng": 106.6578, "address": "Quận 10, TP.HCM"},
        {"name": "ĐH Bách Khoa - Cơ sở 2 (Dĩ An)", "lat": 10.8805, "lng": 106.8063, "address": "Dĩ An, Bình Dương"},
    ]
    a_pick = TurnAnalysis(intent="refine_search", patch=PreferencePatch())

    s_num = make_session()
    s_num.pending_ambiguous_location = "ĐH Bách Khoa"
    s_num.pending_ambiguous_candidates = list(cands)
    plan_num, _ = run(a_pick, session=s_num, text="2")
    assert plan_num.needs_clarification is False
    assert plan_num.preferences.lat == 10.8805
    assert plan_num.preferences.lng == 106.8063

    s_chip = make_session()
    s_chip.pending_ambiguous_location = "ĐH Bách Khoa"
    s_chip.pending_ambiguous_candidates = list(cands)
    plan_chip, _ = run(a_pick, session=s_chip, text="ĐH Bách Khoa - Cơ sở 1 (Quận 10)")
    assert plan_chip.needs_clarification is False
    assert plan_chip.preferences.lat == 10.7726
    assert plan_chip.preferences.lng == 106.6578


def test_budget_clarification_flow_and_invariants():
    from intelligence.nlu import _postprocess

    # 1. NLU báo thiếu số ngân sách mới (dù session đã có lịch sử và max_price=3tr) -> bắt buộc clarify
    s = make_session(pref=UserPreferenceState(location_text="UIT", max_price=3_000_000), messages=["tìm phòng gần UIT 3tr"])
    a_vague_budget = TurnAnalysis(intent="refine_search", needs_budget_clarification=True)
    plan, _ = run(a_vague_budget, session=s, text="tăng giá nữa đi")
    assert plan.needs_clarification is True
    assert plan.needs_budget_clarification is True
    assert plan.preferences.max_price == 3_000_000
    assert route_after_understand({"needs_clarification": plan.needs_clarification}) == "clarification_node"

    # 2. Boundary: nếu LLM đã bóc tách được max_price hoặc clear=['price'] hoặc intent phi tìm kiếm -> tắt cờ clarify ngân sách
    p_with_num = _postprocess(TurnAnalysis(intent="refine_search", patch=PreferencePatch(max_price=4_000_000), needs_budget_clarification=True))
    assert p_with_num.needs_budget_clarification is False

    p_with_clear = _postprocess(TurnAnalysis(intent="refine_search", patch=PreferencePatch(clear=["price"]), needs_budget_clarification=True))
    assert p_with_clear.needs_budget_clarification is False

    p_smalltalk = _postprocess(TurnAnalysis(intent="smalltalk", needs_budget_clarification=True))
    assert p_smalltalk.needs_budget_clarification is False


@pytest.mark.parametrize(
    "query",
    [
        "đại học uit ở đâu",
        "trường bách khoa nằm ở quận mấy",
        "chỉ đường tới đại học uit",
        "học phí uit bao nhiêu",
        "đăng tin cho thuê phòng",
        "mua đất nền Thủ Đức",
        "đặt phòng số 1 giúp mình",
        "giữ phòng top 1 giúp mình",
        "gọi điện cho chủ trọ giúp mình",
        "tìm bạn ở ghép",
    ],
)
def test_off_topic_llm_decision_cleans_payload_and_blocks_without_search(query):
    """Nhóm 1 & 2: Khi LLM phân loại intent='off_topic' (kể cả lỡ kèm patch/semantic_query), _postprocess & interpret_turn dọn sạch và chặn về OFF_TOPIC_QUERY."""
    from intelligence.nlu import _postprocess

    noisy_off_topic = _postprocess(
        TurnAnalysis(
            intent="off_topic",
            page_action="next",
            patch=PreferencePatch(location_text="đại học uit", location_kind="place"),
            semantic_query="tìm phòng gần đại học uit",
        ),
        user_text=query,
    )
    assert noisy_off_topic.intent == "off_topic"
    assert noisy_off_topic.patch.is_empty()
    assert noisy_off_topic.page_action is None
    assert noisy_off_topic.semantic_query is None

    plan, _ = run(noisy_off_topic, text=query)
    assert plan.blocked_reason == "OFF_TOPIC_QUERY"
    assert plan.intent == "off_topic"
    assert plan.commit is False
    assert plan.preferences.location_text is None
    assert route_after_understand({"guardrail_result": type("G", (), {"allowed": False})()}) == "formatter_node"


@pytest.mark.parametrize(
    "query,analysis_obj",
    [
        ("tìm phòng gần đại học uit", TurnAnalysis(intent="new_search", patch=PreferencePatch(location_text="đại học uit", location_kind="place"))),
        ("phòng 1 địa chỉ ở đâu?", TurnAnalysis(intent="room_followup", referenced_room_rank=1)),
        ("phòng 1 cách UIT bao xa?", TurnAnalysis(intent="room_followup", referenced_room_rank=1)),
        ("tìm phòng cho 2 bạn ở ghép gần UIT", TurnAnalysis(intent="new_search", patch=PreferencePatch(location_text="UIT", location_kind="place"))),
        ("lưu ý khi đặt phòng trọ là gì?", TurnAnalysis(intent="skill_advice", skill_slug="rental-contract-advisor")),
    ],
)
def test_valid_housing_queries_with_similar_words_are_not_false_blocked(query, analysis_obj):
    """Nhóm 2 (Boundary): Câu tìm trọ / hỏi chi tiết phòng hợp lệ có chữ 'ở đâu', 'bao xa', 'ở ghép', 'đặt phòng' không bị chặn nhầm."""
    sess = make_session(rooms=[room(1), room(2)])
    plan, _ = run(analysis_obj, session=sess, text=query)
    assert plan.blocked_reason is None
    assert plan.intent != "off_topic"


def test_blocked_unsupported_query_preserves_existing_session_preferences():
    """Nhóm 3 (State Mutation & Zero Leakage): Khi LLM chọn off_topic (dù kèm patch nhiễu) vẫn bị chặn OFF_TOPIC_QUERY, 0 ghi đè preferences, 0 gọi search/geocode."""
    from tests.e2e_helpers import FakeLLM, Harness, nlu

    llm = FakeLLM().on("TurnAnalysis", nlu("off_topic", location_text="đại học uit", location_kind="place"))
    h = Harness(llm, [])
    h.session.preferences = UserPreferenceState(location_text="Quận 7", max_price=4_000_000)
    h.session.last_rooms = [room(1)]

    res = h.turn("đại học uit ở đâu")
    assert h.search_calls == []
    assert h.geo_calls == []
    assert res.rooms == []
    assert h.session.preferences.location_text == "Quận 7"
    assert h.session.preferences.max_price == 4_000_000
    assert [r.id for r in h.session.last_rooms] == ["nhatot_1"]


def test_nlu_postprocess_cleans_default_room_type_noise_on_page_action():
    """Nhóm 4 (NLU Invariant): Khi bật page_action mà patch chỉ dính ROOM/SLEEPBOX mặc định thì dọn sạch patch; giữ nguyên nếu chọn loại phòng khác."""
    from intelligence.nlu import _postprocess

    noisy = TurnAnalysis(
        intent="refine_search",
        page_action="next",
        reset_priorities=True,
        patch=PreferencePatch(allowed_room_types=[RoomType.ROOM], excluded_room_types=[RoomType.SLEEPBOX]),
    )
    cleaned = _postprocess(noisy, user_text="xem các phòng khác đi", n_rooms=10)
    assert cleaned.intent == "page_navigation"
    assert cleaned.patch.is_empty()
    assert cleaned.reset_priorities is False

    studio_change = TurnAnalysis(
        intent="refine_search",
        page_action="next",
        patch=PreferencePatch(allowed_room_types=[RoomType.STUDIO]),
    )
    kept = _postprocess(studio_change, user_text="xem phòng studio khác đi", n_rooms=10)
    assert kept.patch.allowed_room_types == [RoomType.STUDIO]


def test_nlu_postprocess_normalizes_structured_page_navigation_invariants_and_routing():
    """Nhóm 1 & 3: Chuẩn hóa bất biến cấu trúc khi LLM chọn page_navigation hoặc điền page_action mà không dùng regex."""
    from intelligence.nlu import _postprocess

    # 1. LLM điền page_action='goto' nhưng quên đổi intent khỏi refine_search -> chuẩn hóa về page_navigation & dọn semantic_query
    with_action = _postprocess(
        TurnAnalysis(
            intent="refine_search",
            page_action="goto",
            target_page=5,
            semantic_query="tìm phòng ở trang 5",
        ),
        user_text="ok đc rồi zay trang thứ 5 đi",
        n_rooms=24,
    )
    assert with_action.intent == "page_navigation"
    assert with_action.page_action == "goto"
    assert with_action.target_page == 5
    assert with_action.semantic_query is None
    assert with_action.patch.is_empty()

    # 2. LLM chọn intent='page_navigation' nhưng bỏ trống page_action -> mặc định 'next'
    intent_only = _postprocess(
        TurnAnalysis(intent="page_navigation", semantic_query="xem thêm"),
        user_text="xem thêm phòng khác đi",
        n_rooms=24,
    )
    assert intent_only.intent == "page_navigation"
    assert intent_only.page_action == "next"
    assert intent_only.semantic_query is None

    assert route_after_understand({"intent": "page_navigation", "page_switched": True, "direct_reply": False}) == "decision_node"
    assert route_after_understand({"intent": "page_navigation", "page_switched": False, "direct_reply": True}) == "formatter_node"
