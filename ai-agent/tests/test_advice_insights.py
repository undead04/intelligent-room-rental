import pytest

from intelligence.advice import Advice, generate_advice, render_advice
from safety.grounding import parse_vnd_amounts, verify_answer_grounding
from intelligence.insights import build_decision_insights, fmt_money_short, price_trade_off, template_reply
from domain.schemas import UserPreferenceState
from tests.helpers import FakeModel
from tests.test_grounding import R


def rooms3():
    a = R(1, 2_400_000, 25, score=0.874); b = R(2, 2_800_000, 21, score=0.8); c = R(3, 2_400_000, 25, score=0.7)
    a.price, b.price, c.price = "2.4 triệu/tháng", "2.8 triệu/tháng", "2.4 triệu/tháng"
    a.address, b.address = "12 Đường X, Dĩ An", "5 Đường Y"
    return [a, b, c]


@pytest.mark.parametrize("v,s", [(400_000, "400k"), (-400_000, "400k"), (1_250_000, "1.25 triệu"), (3_000_000, "3 triệu"), (450_000, "450k")])
def test_fmt_money_short_roundtrips_through_parser(v, s):
    assert fmt_money_short(v) == s
    assert parse_vnd_amounts(s)[0][1] == abs(v)


def test_price_trade_off_wording():
    a, b, c = rooms3()
    assert price_trade_off(a, b) == "Top 1 rẻ hơn Top 2 khoảng 400k/tháng, rộng hơn 4 m²."
    assert price_trade_off(b, a) == "Top 2 đắt hơn Top 1 khoảng 400k/tháng, nhỏ hơn 4 m²."
    assert price_trade_off(a, c) == "Top 1 và Top 3 có cùng mức giá."
    assert price_trade_off(R(1, 0, None), R(2, 0, None)) == ""


def test_insights_use_percent_and_code_numbers():
    ins = build_decision_insights(rooms3(), weight_explanations=["ưu tiên giá rẻ"])
    assert ins.selected_top_1_id == "nhatot_100" and "87%" in ins.top_1_reason and "ưu tiên giá rẻ" in ins.top_1_reason
    assert "0.87" not in ins.top_1_reason and "boost" not in ins.top_1_reason
    assert len(ins.trade_offs) == 1 and "giá thấp hơn" in ins.trade_offs[0].advantage and len(ins.verification_checklist) == 3
    assert build_decision_insights([]) is None


def test_template_reply_passes_its_own_grounding():
    rooms = rooms3()
    text = template_reply(rooms, build_decision_insights(rooms))
    assert "Giá thuê: 2.4 triệu/tháng" in text and "Điểm phù hợp: 87%" in text and "Diện tích: 25 m²" in text
    r = verify_answer_grounding(text, rooms)
    assert r.is_grounded, r.issues


def test_render_advice_fills_numbers_by_code_and_passes_grounding():
    rooms = rooms3()
    adv = Advice(intro="Mình tìm được vài phòng hợp với bạn nè.", top_reason="Gần điểm bạn muốn và giá dễ chịu.",
                 comparison="Top 1 thoáng hơn, Top 2 yên tĩnh hơn.", checklist=["Hỏi chủ nhà về giờ giấc", "Kiểm tra cách âm"])
    text = render_advice(adv, rooms)
    assert text.startswith("Mình tìm được") and "1. **P1**" in text and "Giá thuê: 2.4 triệu/tháng" in text and "Địa chỉ: 12 Đường X, Dĩ An" in text
    assert "⚖️ **So với Top 2:** Top 1 rẻ hơn Top 2 khoảng 400k/tháng, rộng hơn 4 m². Top 1 thoáng hơn" in text
    assert "- Hỏi chủ nhà về giờ giấc" in text
    assert verify_answer_grounding(text, rooms).is_grounded


def test_render_catches_model_hallucination_in_free_text():
    rooms = rooms3()
    adv = Advice(intro="Phòng rẻ nhất chỉ 1.5 triệu thôi!", top_reason="ok", comparison="", checklist=[])
    r = verify_answer_grounding(render_advice(adv, rooms), rooms)
    assert not r.is_grounded and "1.5 triệu" in r.issues[0]                  # lọt số vào văn bản LLM -> lưới thứ hai bắt được


def test_render_sanitizes_tables_rules_and_lengths_and_defaults():
    adv = Advice(intro="---\n| a | b |\nChào bạn", top_reason="x" * 800, comparison="", checklist=[" ", "a", "b", "c", "d"])
    text = render_advice(adv, [rooms3()[0]])
    assert text.startswith("Chào bạn") and "|" not in text and "…" in text
    assert "⚖️" not in text                                                   # 1 phòng, không có so sánh
    assert text.count("\n- ") >= 3
    empty = render_advice(Advice(intro="", top_reason="", comparison="", checklist=[]), rooms3())
    assert empty.startswith("Homigo đã tìm được 3 phòng") and "Lưu ý khi đi xem phòng" in empty


def test_titles_with_prices_are_evidence_since_code_renders_them_verbatim():
    r = R(1, 2_500_000, 25)
    r.title, r.price = "Phòng 25m2 giá 2tr5 gần chợ", "2.5 triệu/tháng"
    adv = Advice(intro="Chào", top_reason="tốt", comparison="", checklist=["x"])
    assert verify_answer_grounding(render_advice(adv, [r]), [r]).is_grounded


def test_generate_advice_contract():
    rooms = rooms3()
    good = Advice(intro="hi", top_reason="r", comparison="c", checklist=["k"])
    m = FakeModel(good)
    assert generate_advice(m, "SYS", "q", UserPreferenceState(), rooms, retry_issues=["Số tiền không khớp: 9 triệu"], focus_rank=2) is good
    system, human = m.structured.calls[0]
    assert system[1].startswith("SYS") and "KHÔNG viết số tiền" in system[1]
    assert "previous_attempt_issues" in human[1] and "9 triệu" in human[1] and "<focus>" in human[1]
    assert generate_advice(FakeModel({"intro": "a", "top_reason": "b", "comparison": "", "checklist": []}), "S", "q", UserPreferenceState(), rooms).intro == "a"
    assert generate_advice(FakeModel(RuntimeError("x")), "S", "q", UserPreferenceState(), rooms) is None
    assert generate_advice(None, "S", "q", UserPreferenceState(), rooms) is None
    assert generate_advice(m, "S", "q", UserPreferenceState(), []) is None
