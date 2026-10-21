from intelligence.advice import Advice
from tests.e2e_helpers import GOOD_ADVICE, FakeAgent, FakeLLM, Harness, agent_reply, nlu, raw_room

THREE = [raw_room(1, 2_400_000, 25), raw_room(2, 2_800_000, 21), raw_room(3, 3_000_000, 30)]
BAD = Advice(intro="Phòng rẻ nhất chỉ 1.5 triệu thôi!", top_reason="ok", comparison="", checklist=[])


def base_llm(*advices):
    return FakeLLM().on("TurnAnalysis", nlu(location_text="UIT", location_kind="place", max_price=3_500_000)).on("Advice", *advices)


def test_nlu_disabled_never_calls_nlu_and_traces_fallback():
    llm = base_llm(GOOD_ADVICE)
    r = Harness(llm, THREE, nlu_enabled=False).turn("tìm phòng giá rẻ gần UIT")
    assert llm.count("TurnAnalysis") == 0 and any(e["type"] == "nlu_fallback" for e in r.trace_events)
    assert r.need_clarification                              # keyword fallback không trích được địa danh/giá -> hỏi làm rõ


def test_unconstrained_generation_uses_free_text_agent_even_for_new_results():
    llm = base_llm(GOOD_ADVICE)
    agent = FakeAgent(agent_reply("Gợi ý cho bạn: phòng Top 1 khá ổn nhé, nhớ hỏi chủ nhà về giờ giấc."))
    h = Harness(llm, THREE, agent=agent, constrained_generation=False)
    r = h.turn("tìm phòng gần UIT")
    assert llm.count("Advice") == 0 and len(agent.inputs) == 1 and "Top 1 khá ổn" in r.text_reply


def test_unconstrained_without_agent_still_works_via_constrained_path():
    llm = base_llm(GOOD_ADVICE)
    r = Harness(llm, THREE, constrained_generation=False).turn("tìm phòng gần UIT")
    assert llm.count("Advice") == 1 and len(r.rooms) == 3


def test_verification_off_measures_but_does_not_enforce():
    llm = base_llm(BAD, GOOD_ADVICE)
    r = Harness(llm, THREE, verify_answers=False).turn("tìm phòng gần UIT")
    assert llm.count("Advice") == 1 and "1.5 triệu" in r.text_reply                     # ảo giác đi thẳng tới người dùng
    g = r.grounding_report
    assert g.is_grounded is False and g.enforced is False and any("1.5 triệu" in i for i in g.issues) and g.answer_retries == 0 and not g.fallback_template_used


def test_zero_retries_falls_back_to_template_immediately():
    llm = base_llm(BAD, GOOD_ADVICE)
    r = Harness(llm, THREE, max_answer_retries=0).turn("tìm phòng gần UIT")
    assert llm.count("Advice") == 1 and r.grounding_report.fallback_template_used and r.text_reply.startswith("Homigo đã tìm được 3 phòng")


def test_one_retry_budget():
    llm = base_llm(BAD, BAD, GOOD_ADVICE)
    r = Harness(llm, THREE, max_answer_retries=1).turn("tìm phòng gần UIT")
    assert llm.count("Advice") == 2 and r.grounding_report.fallback_template_used
