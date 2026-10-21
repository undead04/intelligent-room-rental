"""Test kiểm thử phân biệt Bắt buộc (Mandatory) vs Ưu tiên (Priority).
Đặc biệt kiểm thử câu: 'Tìm phòng gần UIT dưới 5 triệu có máy lạnh'
và các chốt chặn Deterministic Code Guardrails trong _postprocess.
"""
import pytest
from domain.enums import Amenity, RoomType
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis, apply_patch, _postprocess
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
    # Phương án 3: Khi người dùng chỉ yêu cầu tiện ích bắt buộc ("có máy lạnh"),
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
    processed = _postprocess(analysis, hitl_pending=False, n_rooms=0, valid_slugs=set())
    assert Amenity.NO_SHARED_LANDLORD in processed.patch.amenities_add
    assert processed.patch.special_requirements_add == ["yên tĩnh"]

    pref = apply_patch(UserPreferenceState(), processed.patch)
    assert Amenity.NO_SHARED_LANDLORD in pref.amenities
    assert "Tiện ích BẮT BUỘC" in pref.to_context_string()
    assert "không chung chủ" in pref.to_context_string()


def test_dorm_negation_auto_caught_by_guardrail():
    # Khi LLM bỏ sót room_types_exclude dù người dùng nói "tuyệt đối không lấy ký túc xá hay sleepbox"
    user_prompt = "Tìm phòng trọ ở Bình Thạnh giá dưới 4 triệu, nhưng tuyệt đối không lấy ký túc xá hay sleepbox và không chung chủ nhé"
    analysis = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text="Bình Thạnh",
            max_price=4_000_000,
            room_type=RoomType.ROOM,
            room_types_exclude=[], # Giả sử LLM bỏ sót trường này
        ),
    )
    processed = _postprocess(analysis, user_text=user_prompt, hitl_pending=False, n_rooms=0, valid_slugs=set())
    assert RoomType.SLEEPBOX in processed.patch.room_types_exclude
    assert Amenity.NO_SHARED_LANDLORD in processed.patch.amenities_add


def test_preferred_vs_mandatory_auto_separated_by_guardrail():
    # Khi LLM xếp nhầm tiện ích ưu tiên ("ưu tiên ban công") vào amenities_add (bắt buộc)
    user_prompt = "Tìm phòng gần UIT dưới 5 triệu có máy lạnh, ưu tiên có ban công"
    analysis = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text="UIT",
            max_price=5_000_000,
            amenities_add=[Amenity.AIRCON, Amenity.WINDOW_BALCONY], # LLM nhét cả ban công vào bắt buộc
            preferred_amenities_add=[],
        ),
    )
    processed = _postprocess(analysis, user_text=user_prompt, hitl_pending=False, n_rooms=0, valid_slugs=set())
    assert Amenity.AIRCON in processed.patch.amenities_add
    assert Amenity.WINDOW_BALCONY in processed.patch.preferred_amenities_add
    assert Amenity.WINDOW_BALCONY not in processed.patch.amenities_add


def test_price_fallback_regex_guardrail():
    # Khi LLM bỏ sót max_price dù người dùng nói "dưới 4 triệu"
    user_prompt = "Tìm phòng trọ ở Bình Thạnh dưới 4 triệu"
    analysis = TurnAnalysis(
        intent="new_search",
        patch=PreferencePatch(
            location_text="Bình Thạnh",
            max_price=None, # LLM bỏ sót
        ),
    )
    processed = _postprocess(analysis, user_text=user_prompt, hitl_pending=False, n_rooms=0, valid_slugs=set())
    assert processed.patch.max_price == 4_000_000
