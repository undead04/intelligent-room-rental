"""Test kiểm thử phân biệt Bắt buộc (Mandatory) vs Ưu tiên (Priority).
Đặc biệt kiểm thử câu: 'Tìm phòng gần UIT dưới 5 triệu có máy lạnh'
và các chốt chặn cấu trúc trạng thái trong _postprocess.
"""
from domain.enums import Amenity
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import PreferencePatch, TurnAnalysis, apply_patch, _postprocess
from domain.schemas import RoomItem, UserPreferenceState
from safety.grounding import check_hard_constraints


def test_mandatory_vs_preferred_amenities_patch():
    pref = UserPreferenceState()
    
    # 1. "có máy lạnh": tiện ích bắt buộc
    patch_mandatory = PreferencePatch(
        location_text="UIT",
        max_price=5_000_000,
        amenities_add=["aircon"],
    )
    p1 = apply_patch(pref, patch_mandatory)
    assert p1.amenities == [Amenity.AIRCON]
    assert p1.preferred_amenities == []
    assert p1.max_price == 5_000_000
    assert p1.location_text == "UIT"

    # Context string phải tách biệt BẮT BUỘC vs ƯU TIÊN
    ctx = p1.to_context_string()
    assert "Tiện ích BẮT BUỘC" in ctx
    assert "máy lạnh" in ctx
    assert "ƯU TIÊN" not in ctx

    # 2. "ưu tiên có ban công, có máy giặt càng tốt": tiện ích ưu tiên mềm
    patch_preferred = PreferencePatch(
        preferred_amenities_add=["window_balcony", "washing_machine"],
    )
    p2 = apply_patch(p1, patch_preferred)
    assert p2.amenities == [Amenity.AIRCON]
    assert p2.preferred_amenities == [Amenity.WINDOW_BALCONY, Amenity.WASHING_MACHINE]

    ctx2 = p2.to_context_string()
    assert "Tiện ích BẮT BUỘC" in ctx2
    assert "Tiện ích ƯU TIÊN" in ctx2


def test_normalized_weights_not_boosted_for_regular_amenity():
    # Khi người dùng chỉ yêu cầu tiện ích bắt buộc ("có máy lạnh"),
    # tiện ích bắt buộc đã được lọc cứng ở SQL & Grounding nên tắt hẳn trọng số 'amenity' trong MCDM
    p = UserPreferenceState(lat=10.87, lng=106.8, max_price=5_000_000, amenities=["aircon"])
    multipliers = {"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0}

    w = compute_normalized_weights(p, multipliers)
    assert "amenity" not in w
    assert set(w.keys()) == {"price", "location", "safety", "semantic"}
    assert abs(sum(w.values()) - 1.0) < 1e-4

    # Chỉ khi có preferred_amenities hoặc có ý định nhấn mạnh tổng thể thì amenity mới được bật
    p_pref = UserPreferenceState(lat=10.87, lng=106.8, max_price=5_000_000, amenities=["aircon"], preferred_amenities=["window_balcony"])
    w_pref = compute_normalized_weights(p_pref, multipliers)
    assert "amenity" in w_pref
    assert w_pref["amenity"] == 0.2


def test_grounding_hard_constraints_filters_room_without_aircon():
    pref = UserPreferenceState(max_price=5_000_000, amenities=["aircon"])

    room_with_ac = RoomItem(
        id="room_1",
        title="Phòng trọ có máy lạnh",
        price="4 triệu/tháng",
        priceNum=4_000_000,
        concept_scores={"aircon": 0.95, "private_wc": 0.9},
    )
    room_without_ac = RoomItem(
        id="room_2",
        title="Phòng trọ không máy lạnh",
        price="3 triệu/tháng",
        priceNum=3_000_000,
        concept_scores={"aircon": 0.1, "private_wc": 0.9},
    )
    room_over_budget = RoomItem(
        id="room_3",
        title="Phòng trọ VIP vượt giá",
        price="6 triệu/tháng",
        priceNum=6_000_000,
        concept_scores={"aircon": 1.0},
    )

    valid, dropped = check_hard_constraints([room_with_ac, room_without_ac, room_over_budget], pref)
    
    valid_ids = [r.id for r in valid]
    assert valid_ids == ["room_1"]
    
    dropped_reasons = dict(dropped)
    assert "room_2" in dropped_reasons
    assert "thiếu tiện ích bắt buộc" in dropped_reasons["room_2"]
    assert "room_3" in dropped_reasons
    assert "vượt ngân sách" in dropped_reasons["room_3"]


def test_no_shared_landlord_promoted_from_special_requirements():
    analysis = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text="Bình Thạnh",
            max_price=4_000_000,
            special_requirements_add=["không chung chủ", "yên tĩnh"],
        ),
    )
    processed = _postprocess(analysis, n_rooms=0, valid_slugs=set())
    assert Amenity.NO_SHARED_LANDLORD in processed.patch.amenities_add
    assert processed.patch.special_requirements_add == ["yên tĩnh"]

    pref = apply_patch(UserPreferenceState(), processed.patch)
    assert Amenity.NO_SHARED_LANDLORD in pref.amenities
    assert "Tiện ích BẮT BUỘC" in pref.to_context_string()
    assert "không chung chủ" in pref.to_context_string()
