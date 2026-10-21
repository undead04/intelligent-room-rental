import json

import pytest
from pydantic import ValidationError

from domain.enums import Amenity, RoomType
from domain.schemas import (
    AgentResponse,
    GroundingReport,
    HitlOption,
    RoomItem,
    UserPreferenceState,
    format_vnd_million,
)


# ---------------- UserPreferenceState ----------------
def test_assigning_amenities_normalizes():
    p = UserPreferenceState()
    p.amenities = ["máy lạnh", "xyz", "ml", "gác"]          # đúng lỗi cũ: tiếng Việt bị lọc mất
    assert p.amenities == [Amenity.AIRCON, Amenity.MEZZANINE]


def test_constructor_normalizes():
    p = UserPreferenceState(amenities=["AC", "camera"], room_type="ktx", excluded_room_types=["studio", "bậy"])
    assert p.amenities == [Amenity.AIRCON, Amenity.CAMERA]
    assert p.room_type is RoomType.SLEEPBOX
    assert p.excluded_room_types == [RoomType.STUDIO]


def test_room_type_assignment_and_id_property():
    p = UserPreferenceState()
    assert p.room_type_id is None
    p.room_type = "SLEEPBOX"
    assert p.room_type is RoomType.SLEEPBOX and p.room_type_id == 4
    p.room_type = "không có loại này"
    assert p.room_type is None and p.room_type_id is None


def test_room_type_id_is_read_only():
    p = UserPreferenceState()
    with pytest.raises((ValueError, AttributeError, ValidationError)):
        p.room_type_id = 4  # type: ignore[misc]


def test_has_point_and_has_admin():
    p = UserPreferenceState()
    assert not p.has_point and not p.has_admin
    p.lat = 10.8
    assert not p.has_point
    p.lng = 106.7
    assert p.has_point
    p.district_id = 5
    assert p.has_admin


def test_set_location_clears_everything_old():
    p = UserPreferenceState(location_text="Dĩ An", lat=10.9, lng=106.7, city_id=74, district_id=724, ward_id=1)
    p.set_location("Quận 7", city_id=79, district_id=778)
    assert p.location_text == "Quận 7"
    assert (p.city_id, p.district_id) == (79, 778)
    assert p.lat is None and p.lng is None and p.ward_id is None


def test_set_location_rejects_unknown_keys_and_clear():
    p = UserPreferenceState(location_text="x", lat=1.0, lng=2.0, city_id=1)
    with pytest.raises(TypeError):
        p.set_location("y", foo=1)
    p.clear_location()
    assert p.location_text is None and not p.has_point and not p.has_admin


def test_model_copy_deep_is_independent():
    a = UserPreferenceState(amenities=["ml"], max_price=3_000_000)
    b = a.model_copy(deep=True)
    b.amenities = ["camera"]
    b.max_price = 4_000_000
    assert a.amenities == [Amenity.AIRCON] and a.max_price == 3_000_000


def test_to_context_string():
    assert UserPreferenceState().to_context_string() == "Chưa có tiêu chí nào được thiết lập."
    p = UserPreferenceState(
        location_text="UIT", lat=10.87, lng=106.8, max_price=3_500_000, amenities=["ml"],
        room_type="studio", excluded_room_types=["ktx"], min_area=20,
    )
    s = p.to_context_string()
    assert "UIT" in s and "3.5 tr/tháng" in s and "aircon" in s
    assert "căn hộ studio" in s and "ký túc xá sleepbox" in s and "20–?" in s


def test_json_roundtrip_serializes_enums_as_values():
    p = UserPreferenceState(amenities=["ml"], room_type="ktx")
    d = json.loads(p.model_dump_json())
    assert d["amenities"] == ["aircon"] and d["room_type"] == "SLEEPBOX"
    assert UserPreferenceState.model_validate(d) == p


# ---------------- RoomItem ----------------
def _raw(**listing):
    base = {"id": "nhatot_1", "title": "Phòng A", "price_vnd": 2_750_000, "area_m2": 25.0,
            "address_raw": "12 Đường X, Dĩ An", "lat": 10.9, "lng": 106.75, "main_image": "http://img/1.jpg",
            "images": ["a", "b", "c"]}
    base.update(listing)
    return {"listing": base, "match_score": 0.8734, "explain_match": {"top_factors": [{"name": "price"}, {"name": "safety"}]}}


def test_room_item_basic_mapping():
    r = RoomItem.from_backend_result(_raw(), rank=1, target_lat=10.9, target_lng=106.75)
    assert r.id == "nhatot_1" and r.priceNum == 2_750_000
    assert r.price == "2.75 triệu/tháng"                    # nhất quán với format_vnd_million
    assert r.area_m2 == 25.0 and "25 m²" in r.tags
    assert r.photoCount == 3 and r.address == "12 Đường X, Dĩ An"
    assert r.matchScore == 0.873 and r.match_percent == 87
    assert r.rankText == "Top 1 - Tối ưu nhất"
    assert r.tags[-2:] == ["Giá tốt", "An ninh cao"]
    assert r.distance == "50m"                              # cùng toạ độ -> sàn 50m


def test_room_item_does_not_invent_missing_data():
    r = RoomItem.from_backend_result({"listing": {"id": "z", "title": "T", "price_vnd": 0}, "match_score": 0.5})
    assert r.address == ""                                   # không còn 'Hồ Chí Minh'
    assert r.photoCount == 0                                 # không còn 4 ảnh ảo
    assert r.distance == ""                                  # không nhét địa chỉ vào khoảng cách
    assert r.price == "Thỏa thuận" and r.area_m2 is None


def test_room_item_price_string_fallback():
    r = RoomItem.from_backend_result({"listing": {"id": "z", "price_vnd": 0, "price_string": "Liên hệ"}})
    assert r.price == "Liên hệ"


def test_inferred_tags_separate_and_balcony_key_fixed():
    r = RoomItem.from_backend_result(_raw(concept_scores={"aircon": 0.9, "window_balcony": 0.8, "mezzanine": 0.5, "balcony": 0.9}))
    assert r.inferred_tags == ["Có máy lạnh", "Có ban công"]   # 'balcony' + 'window_balcony' không bị lặp
    assert "Có máy lạnh" not in r.tags


def test_distance_formats():
    r1 = RoomItem.from_backend_result(_raw(distance_km=0.456))
    r2 = RoomItem.from_backend_result(_raw(distance_km=2.34))
    r3 = RoomItem.from_backend_result(_raw(distance="~800m"))
    assert (r1.distance, r2.distance, r3.distance) == ("460m", "2.3 km", "800m")


def test_pin_positions_are_deterministic():
    a = RoomItem.from_backend_result(_raw(), rank=2)
    b = RoomItem.from_backend_result(_raw(), rank=2)
    assert (a.latPercent, a.lngPercent) == (b.latPercent, b.lngPercent)
    assert 40.0 <= a.latPercent < 65.0 and 35.0 <= a.lngPercent < 70.0


def test_match_percent_handles_both_scales():
    assert RoomItem(id="a", title="t", price="p", matchScore=0.5).match_percent == 50
    assert RoomItem(id="a", title="t", price="p", matchScore=87.0).match_percent == 87


def test_match_percent_in_dump():
    d = RoomItem(id="a", title="t", price="p", matchScore=0.5).model_dump(mode="json")
    assert d["match_percent"] == 50


# ---------------- HITL / Response ----------------
def test_hitl_option_action_optional_and_action_text_default():
    o = HitlOption(id="adjust_budget", type="budget", title="t", description="d", action="relax_budget")
    assert o.action.value == "relax_budget" and o.action_text == ""
    assert HitlOption(id="x", type="t", title="t", description="d").action is None


def test_agent_response_accepts_legacy_grounding_dict():
    legacy = {"is_grounded": True, "context_grounded": False, "needs_user_consent": True,
              "hitl_streak": 1, "hitl_max_streak": 2, "something_new": 7}
    resp = AgentResponse(text_reply="hi", grounding_report=legacy, current_preferences=UserPreferenceState(amenities=["ml"]))
    assert isinstance(resp.grounding_report, GroundingReport)
    assert resp.grounding_report.hitl_streak == 1
    assert resp.model_dump(mode="json")["grounding_report"]["something_new"] == 7   # khoá lạ không mất


def test_format_vnd_million():
    assert format_vnd_million(3_500_000) == "3.5 triệu/tháng"
    assert format_vnd_million(3_000_000) == "3 triệu/tháng"
    assert format_vnd_million(2_750_000) == "2.75 triệu/tháng"
    assert format_vnd_million(500_000) == "500,000 đ/tháng"
    assert format_vnd_million(0) == "Thỏa thuận" and format_vnd_million(None) == "Thỏa thuận"
