import pytest

from domain.budget import MarketStats
from domain.enums import Amenity, HitlAction, RoomType
from safety.grounding import (
    ClaimsReport, check_hard_constraints, critic_unsupported_claims, find_format_violations, parse_areas,
    parse_vnd_amounts, verify_answer_grounding, verify_context_grounding, build_hitl_proposal,
)
from domain.schemas import RoomItem, UserPreferenceState
from tests.helpers import FakeModel


def R(i, price=2_500_000, area=25.0, rt=None, score=0.8):
    return RoomItem(id=f"nhatot_{i}00", rank=i, title=f"P{i}", price="x", priceNum=price, area_m2=area, room_type=rt, matchScore=score)


# ---------------- parser ----------------
@pytest.mark.parametrize("text,expected", [
    ("giá 2tr5", [2_500_000]), ("3 triệu rưỡi", [3_500_000]), ("2.8 triệu/tháng", [2_800_000]), ("2,75 triệu", [2_750_000]),
    ("800k", [800_000]), ("300 nghìn", [300_000]), ("cọc 2.500.000đ", [2_500_000]), ("cọc 2.500.000 đồng", [2_500_000]),
    ("2.500.000", [2_500_000]), ("500.000đ", [500_000]), ("2500000 đ", [2_500_000]),
    ("2.500", []),                 # mơ hồ -> bỏ
    ("5 km, 3 phòng, 90%", []), ("trong 25 phút", []), ("điểm 87 đ", []), ("5k", []),    # nhiễu < 10.000
    ("nhatot_134860847", []), ("2 triệu và 3 triệu", [2_000_000, 3_000_000]),
    ("khoảng 1tr2 đến 1tr5", [1_200_000, 1_500_000]),
])
def test_parse_vnd_amounts(text, expected):
    assert [v for _, v in parse_vnd_amounts(text)] == expected


def test_parse_areas():
    assert [v for _, v in parse_areas("25 m², 30m2, 18,5 m2 và 40 mét vuông")] == [25, 30, 18.5, 40]
    assert parse_areas("cách 25 km, 25 phòng") == []


# ---------------- verify_answer_grounding ----------------
def test_clean_answer_passes_and_scores_one():
    rooms = [R(1, 2_800_000, 25), R(2, 2_400_000, 20)]
    ans = "Top 1: P1, giá 2.8 triệu/tháng, 25 m². Top 2 rẻ hơn 400k, 20m2."
    r = verify_answer_grounding(ans, rooms)
    assert r.is_grounded and r.groundedness_score == 1.0 and r.checked == r.verified == 4


def test_hallucinated_id_price_area_detected():
    rooms = [R(1, 2_800_000, 25)]
    r = verify_answer_grounding("Phòng nhatot_999 giá 3.9 triệu, rộng 40 m², cọc 1.500.000đ.", rooms)
    assert not r.is_grounded and len(r.issues) == 3
    joined = " ".join(r.issues)
    assert "nhatot_999" in joined and "3.9 triệu" in joined and "1.500.000đ" in joined and "40 m²" in joined
    assert r.groundedness_score < 1.0


def test_price_tolerance_and_rounding():
    rooms = [R(1, 2_750_000)]
    assert verify_answer_grounding("giá 2.8 triệu", rooms).is_grounded                # lệch 50k: ok
    assert not verify_answer_grounding("giá 3 triệu", rooms).is_grounded              # làm tròn lố
    assert verify_answer_grounding("giá 2.75 triệu và 2tr75", rooms).is_grounded


def test_known_id_is_accepted_but_unknown_with_same_prefix_is_not():
    rooms = [R(1)]
    assert verify_answer_grounding("xem NHATOT_100 nhé", rooms).is_grounded          # không phân biệt hoa/thường
    assert not verify_answer_grounding("xem nhatot_200 nhé", rooms).is_grounded
    assert verify_answer_grounding("Top-1 là phòng tốt", rooms).is_grounded           # 'Top-1' không phải mã phòng
    r = RoomItem(id="abc_123", title="t", price="p")
    assert not verify_answer_grounding("xem abc_999", [r]).is_grounded                # tiền tố suy ra từ dữ liệu


def test_budget_and_pair_differences_are_valid_evidence():
    rooms = [R(1, 2_800_000), R(2, 2_400_000)]
    pref = UserPreferenceState(max_price=3_500_000, min_area=18)
    r = verify_answer_grounding("Ngân sách 3.5 triệu, Top 2 rẻ hơn 400k, diện tích tối thiểu 18 m².", rooms, pref)
    assert r.is_grounded


def test_tool_output_counts_as_evidence():
    rooms = [R(1)]
    tool = '{"ok": true, "data": {"deposit": 3000000, "service_fee": "200.000đ", "area": "27 m2"}}'
    ans = "Cọc 3 triệu, phí dịch vụ 200k, diện tích 27 m²."
    assert not verify_answer_grounding(ans, rooms).is_grounded                         # không có bằng chứng -> báo lỗi
    assert verify_answer_grounding(ans, rooms, extra_texts=[tool]).is_grounded         # có kết quả get_listing_detail -> hợp lệ


def test_extra_amounts_for_proposals():
    assert verify_answer_grounding("Nới lên 3.45 triệu nhé", [R(1)], extra_amounts=[3_450_000]).is_grounded
    assert not verify_answer_grounding("Nới lên 3.45 triệu nhé", [R(1)]).is_grounded


def test_no_rooms_context():
    assert verify_answer_grounding("Bạn thử nới ngân sách nhé", []).is_grounded
    r = verify_answer_grounding("Phòng nhatot_123 giá 2 triệu", [])
    assert not r.is_grounded and len(r.issues) == 2


def test_empty_answer():
    r = verify_answer_grounding("   ", [R(1)])
    assert not r.is_grounded and r.groundedness_score == 0.0


def test_format_violations_become_issues():
    ans = "Tổng hợp:\n| Phòng | Giá |\n| --- | --- |\n---\nXong"
    assert find_format_violations(ans) == ["Định dạng: dùng bảng Markdown", "Định dạng: dùng đường kẻ ngang"]
    r = verify_answer_grounding(ans, [R(1)])
    assert not r.is_grounded and any("bảng" in i for i in r.issues)
    assert find_format_violations("- gạch đầu dòng\n1. đánh số\na | b") == []


# ---------------- hard constraints / context grounding ----------------
def test_hard_constraints_drop_and_renumber():
    pref = UserPreferenceState(max_price=3_000_000, min_area=20, excluded_room_types=["ktx"])
    rooms = [R(1, 3_500_000), R(2, 2_900_000, 15), R(3, 2_000_000, 30, rt=RoomType.SLEEPBOX), R(4, 2_000_000, 22), R(5, 0, None)]
    valid, dropped = check_hard_constraints(rooms, pref)
    assert [r.id for r in valid] == ["nhatot_400", "nhatot_500"]          # giá/diện tích unknown (0/None) KHÔNG bị loại
    assert [r.rank for r in valid] == [1, 2]
    reasons = dict(dropped)
    assert "vượt ngân sách" in reasons["nhatot_100"] and "nhỏ hơn" in reasons["nhatot_200"] and "loại trừ" in reasons["nhatot_300"]


def test_price_filter_tolerance():
    pref = UserPreferenceState(max_price=3_000_000)
    valid, _ = check_hard_constraints([R(1, 3_050_000), R(2, 3_100_000)], pref)
    assert [r.id for r in valid] == ["nhatot_100"]                          # 1.7% ok, 3.3% loại


def test_context_ok_returns_valid_rooms_and_top_score():
    res = verify_context_grounding([R(1, score=0.7), R(2, score=0.9)], UserPreferenceState(max_price=3_000_000))
    assert res.is_grounded and not res.needs_user_consent and res.context_score == 0.9 and len(res.valid_rooms) == 2


def test_context_empty_triggers_hitl():
    res = verify_context_grounding([], UserPreferenceState(max_price=3_000_000, location_text="Dĩ An"))
    assert not res.is_grounded and res.needs_user_consent and res.hitl_proposal
    assert res.proposed_budget == 3_450_000 and res.proposed_budget_str == "3.45 triệu/tháng"


def test_context_all_violating_also_triggers_hitl_with_dropped():
    res = verify_context_grounding([R(1, 9_000_000)], UserPreferenceState(max_price=3_000_000))
    assert res.needs_user_consent and res.dropped and "vi phạm" in res.reason


# ---------------- HITL proposal ----------------
def _fetcher(min_price=2_000_000, total=100):
    calls = []
    def f(**kw):
        calls.append(kw)
        return {"minimum_price_vnd": min_price, "average_price_vnd": 3_200_000, "total_listings": total}
    f.calls = calls
    return f


def _actions(p):
    return [o.action for o in p.options]


def test_hitl_market_gap_with_real_stats():
    pref = UserPreferenceState(max_price=1_500_000, location_text="Quận 1", city_id=79, district_id=1)
    p = build_hitl_proposal(pref, market_fetcher=_fetcher())
    assert p.is_market_gap and p.proposed_budget == 2_000_000 and p.market_min_price_str == "2 triệu/tháng"
    assert "Tại Quận 1" in p.message and p.options[0].highlight and p.options[0].action is HitlAction.RELAX_BUDGET
    assert HitlAction.DORMITORY in _actions(p)


def test_hitl_never_invents_market_data_when_backend_has_none():
    pref = UserPreferenceState(max_price=1_200_000, location_text="Quận 1", city_id=79)
    for fetcher in (lambda **kw: None, None):
        p = build_hitl_proposal(pref, market_fetcher=fetcher)
        assert not p.is_market_gap and p.market_min_price is None and p.market_avg_price is None
        assert p.proposed_budget == 1_400_000 and "thấp nhất ghi nhận" not in (p.message or "")


def test_hitl_no_city_means_no_market_call():
    f = _fetcher()
    p = build_hitl_proposal(UserPreferenceState(max_price=1_500_000, lat=10.8, lng=106.7), market_fetcher=f)   # tìm theo toạ độ, không rõ thành phố
    assert f.calls == [] and not p.is_market_gap


def test_hitl_room_type_passed_to_fetcher():
    f = _fetcher()
    build_hitl_proposal(UserPreferenceState(max_price=3e6, city_id=79, room_type="studio"), market_fetcher=f)
    assert f.calls[0]["room_type_id"] == 2
    f2 = _fetcher()
    build_hitl_proposal(UserPreferenceState(max_price=3e6, city_id=79), {"room_type": "ROOM", "district_id": 5}, market_fetcher=f2)
    assert f2.calls[0] == {"city_id": 79, "district_id": 5, "room_type_id": 1}


def test_hitl_dormitory_hidden_when_excluded_or_budget_high():
    p = build_hitl_proposal(UserPreferenceState(max_price=1_800_000, excluded_room_types=["ktx"]))
    assert HitlAction.DORMITORY not in _actions(p)
    assert HitlAction.DORMITORY not in _actions(build_hitl_proposal(UserPreferenceState(max_price=3_000_000)))
    assert HitlAction.DORMITORY in _actions(build_hitl_proposal(UserPreferenceState(max_price=1_800_000)))


def test_hitl_broaden_only_when_there_is_a_location():
    assert HitlAction.BROADEN not in _actions(build_hitl_proposal(UserPreferenceState(max_price=3e6)))
    assert HitlAction.BROADEN in _actions(build_hitl_proposal(UserPreferenceState(max_price=3e6, location_text="Dĩ An")))
    p = build_hitl_proposal(UserPreferenceState(max_price=3e6, ward_id=7), {"ward_id": 7})
    assert [o for o in p.options if o.action is HitlAction.BROADEN][0].title == "Mở rộng ra toàn Quận/Huyện"


def test_hitl_reduce_amenities_uses_vietnamese_labels_and_always_has_keep_custom():
    p = build_hitl_proposal(UserPreferenceState(max_price=3e6, amenities=["ml", "gác", "camera"]))
    o = [x for x in p.options if x.action is HitlAction.REDUCE_AMENITIES][0]
    assert "máy lạnh, gác lửng" in o.title and "aircon" not in o.title
    assert _actions(p)[-2:] == [HitlAction.KEEP, HitlAction.CUSTOM]
    assert all(x.action is not None and x.action_text for x in p.options)


def test_hitl_without_budget_has_no_budget_option():
    p = build_hitl_proposal(UserPreferenceState(location_text="Dĩ An"))
    assert HitlAction.RELAX_BUDGET not in _actions(p) and p.proposed_budget is None


# ---------------- critic ----------------
def test_critic_returns_claims_and_never_raises():
    m = FakeModel(ClaimsReport(unsupported_claims=["Phòng 1 yên tĩnh", " ", "Gần chợ"]))
    assert critic_unsupported_claims(m, "Phòng 1 yên tĩnh, gần chợ", [R(1)]) == ["Phòng 1 yên tĩnh", "Gần chợ"]
    assert critic_unsupported_claims(FakeModel({"unsupported_claims": ["a"]}), "x", [R(1)]) == ["a"]
    assert critic_unsupported_claims(FakeModel(RuntimeError("down")), "x", [R(1)]) == []
    assert critic_unsupported_claims(None, "x", [R(1)]) == []
    assert critic_unsupported_claims(FakeModel(ClaimsReport()), "  ", [R(1)]) == []
    human = m.structured.calls[0][1][1]
    assert "<rooms_data>" in human and "<answer>" in human


# ---------------- khoảng cách ----------------
from safety.grounding import parse_distances


@pytest.mark.parametrize("text,expected", [
    ("cách 450m", [450]), ("1.2 km", [1200]), ("1,5km", [1500]), ("300 mét", [300]), ("25 m², 25m2, 40 mét vuông", []),
    ("12m", []), ("cách 5 km, sau 800m", [5000, 800]), ("phòng cách UIT 2.5 km", [2500]), ("bán kính 1km", [1000]),
])
def test_parse_distances(text, expected):
    assert [v for _, v in parse_distances(text)] == expected


def _dr(i, dist):
    r = R(i)
    r.distance = dist
    return r


def test_distance_claims_checked_against_room_data_with_tolerance():
    rooms = [_dr(1, "450m"), _dr(2, "1.2 km")]
    assert verify_answer_grounding("Top 1 cách điểm bạn chọn 450m, Top 2 cách 1.2 km.", rooms).is_grounded
    assert verify_answer_grounding("Top 1 cách khoảng 480m", rooms).is_grounded                    # trong dung sai 15%/50m
    assert verify_answer_grounding("Top 2 cách khoảng 1.3 km", rooms).is_grounded
    r = verify_answer_grounding("Top 1 chỉ cách 100m thôi, gần lắm", rooms)
    assert not r.is_grounded and "Khoảng cách không khớp" in r.issues[0] and "100m" in r.issues[0]
    assert not verify_answer_grounding("Top 2 cách 3 km", rooms).is_grounded


def test_distance_not_confused_with_area_or_missing_data():
    rooms = [_dr(1, "")]
    assert verify_answer_grounding("Phòng rộng 25 m² nằm trong hẻm 3m", rooms).is_grounded          # '3m' < 30m = nhiễu, '25 m²' là diện tích
    assert not verify_answer_grounding("Phòng cách chợ 500m", rooms).is_grounded                    # không có dữ liệu khoảng cách -> không có căn cứ


def test_user_stated_distance_may_be_echoed_but_not_other_numbers():
    rooms = [_dr(1, "450m")]
    assert verify_answer_grounding("Trong bán kính 2km mình thấy 1 phòng.", rooms, user_text="tìm phòng trong bán kính 2km").is_grounded
    assert not verify_answer_grounding("Trong bán kính 2km mình thấy 1 phòng.", rooms).is_grounded
    assert not verify_answer_grounding("Có phòng cách 3km", rooms, user_text="tìm phòng trong bán kính 2km").is_grounded


def test_distance_from_tool_evidence_is_valid():
    assert verify_answer_grounding("Chợ gần nhất cách khoảng 200 mét.", [_dr(1, "450m")], extra_texts=['{"nearby": "chợ cách 200m"}']).is_grounded


def test_rendered_room_lines_pass_distance_check():
    from intelligence.insights import template_reply
    rooms = [_dr(1, "450m"), _dr(2, "1.2 km")]
    assert verify_answer_grounding(template_reply(rooms, None), rooms).is_grounded
