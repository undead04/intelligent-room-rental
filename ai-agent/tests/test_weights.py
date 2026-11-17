import itertools
import random

import pytest

from intelligence.intent_weights import compute_normalized_weights
from domain.schemas import UserPreferenceState

CRITERIA = ("price", "location", "safety", "amenity", "semantic")


def _pref(has_point: bool, has_amen: bool, has_admin: bool = False) -> UserPreferenceState:
    p = UserPreferenceState()
    if has_point:
        p.lat, p.lng = 10.87, 106.80
    if has_amen:
        p.preferred_amenities = ["ml"]
    if has_admin:
        p.district_id = 5
    return p


@pytest.mark.parametrize("has_point,has_amen", list(itertools.product([False, True], repeat=2)))
def test_sum_is_one_and_non_negative_for_random_multipliers(has_point, has_amen):
    rng = random.Random(42)
    for _ in range(300):
        mult = {k: rng.choice([0.0, 0.5, 1.0, 1.8, 2.0, 3.0, rng.uniform(0.01, 5)]) for k in CRITERIA}
        w = compute_normalized_weights(_pref(has_point, has_amen), mult)
        assert abs(sum(w.values()) - 1.0) < 1e-9, (mult, w)
        assert all(v >= 0 for v in w.values())


def test_active_keys_follow_preferences():
    ones = {k: 1.0 for k in CRITERIA}
    # Không có tọa độ và không nhắc an ninh -> chỉ bật price, semantic, amenity (mức nền)
    w_basic = compute_normalized_weights(_pref(False, False), ones)
    assert set(w_basic) == {"price", "semantic", "amenity"}
    assert "safety" not in w_basic
    assert w_basic["amenity"] < w_basic["price"]
    assert w_basic["semantic"] == pytest.approx(w_basic["amenity"])

    # Có tọa độ -> bật thêm location; không nhắc an ninh -> safety vẫn tắt
    w_loc = compute_normalized_weights(_pref(True, False), ones)
    assert set(w_loc) == {"price", "location", "semantic", "amenity"}
    assert w_loc["amenity"] < w_loc["location"]
    assert w_loc["semantic"] == pytest.approx(w_loc["amenity"])

    # Có tiện ích mềm -> amenity nâng mức đầy đủ (0.20 trước chuẩn hóa)
    w_amen = compute_normalized_weights(_pref(False, True), ones)
    assert set(w_amen) == {"price", "semantic", "amenity"}
    assert w_amen["amenity"] < w_amen["price"]
    assert w_amen["semantic"] < w_amen["amenity"]

    # Nhắc ưu tiên an ninh (safety > 1.0) + có tọa độ + tiện ích mềm -> đủ cả 5 trụ cột
    mult_safety = {**ones, "safety": 1.5}
    w_with_safety = compute_normalized_weights(_pref(True, True), mult_safety)
    assert set(w_with_safety) == set(CRITERIA)

    # Khi chỉ bật safety qua tiện ích an ninh (không phóng đại multiplier) -> khớp bộ cơ sở 5 trụ cột
    p_safe_full = UserPreferenceState(
        lat=10.87,
        lng=106.80,
        preferred_amenities=["ml", "safe_area"],
    )
    w_full = compute_normalized_weights(p_safe_full, ones)
    assert set(w_full) == set(CRITERIA)
    assert w_full == pytest.approx({"location": 0.25, "price": 0.25, "safety": 0.20, "amenity": 0.20, "semantic": 0.10})


def test_safety_enabled_only_when_mentioned():
    """Trụ cột safety chỉ bật khi người dùng nhắc an ninh/an toàn hoặc chọn tiện ích an ninh."""
    ones = {k: 1.0 for k in CRITERIA}
    # Không nhắc -> tắt hoàn toàn
    w_plain = compute_normalized_weights(UserPreferenceState(lat=10.87, lng=106.80, amenities=["aircon"]), ones)
    assert "safety" not in w_plain

    # Nhắc qua mức ưu tiên (NLU priorities.safety = 'high' -> multiplier > 1) -> bật
    w_mult = compute_normalized_weights(UserPreferenceState(lat=10.87, lng=106.80), {**ones, "safety": 2.0})
    assert "safety" in w_mult and w_mult["safety"] > 0.20

    # Nhắc qua tiện ích an ninh bắt buộc hoặc mềm -> bật
    for am in ("safe_area", "camera", "guard", "fingerprint_lock"):
        w_am = compute_normalized_weights(UserPreferenceState(amenities=[am]), ones)
        assert "safety" in w_am and w_am["safety"] > 0.0, am


def test_mandatory_amenities_alone_do_not_boost_amenity_weight():
    p = UserPreferenceState(amenities=["aircon", "no_shared_landlord"])
    w = compute_normalized_weights(p, {k: 1.0 for k in CRITERIA})
    p_pref = UserPreferenceState(amenities=["aircon"], preferred_amenities=["window_balcony"])
    w_pref = compute_normalized_weights(p_pref, {k: 1.0 for k in CRITERIA})
    assert w["amenity"] < w["price"]
    assert w["amenity"] < w_pref["amenity"]


def test_admin_ids_alone_do_not_enable_location():
    w = compute_normalized_weights(_pref(False, False, has_admin=True), {k: 1.0 for k in CRITERIA})
    assert "location" not in w


def test_amenity_enabled_even_when_user_typed_vietnamese_preferred():
    p = UserPreferenceState()
    p.preferred_amenities = ["máy lạnh"]
    assert "amenity" in compute_normalized_weights(p, {k: 1.0 for k in CRITERIA})


def test_boost_raises_share():
    p = _pref(True, True)
    base = compute_normalized_weights(p, {k: 1.0 for k in CRITERIA})
    boosted = compute_normalized_weights(p, {**{k: 1.0 for k in CRITERIA}, "price": 2.0})
    assert boosted["price"] > base["price"]


def test_all_zero_falls_back_to_equal_and_negative_is_clamped():
    p = _pref(True, True)
    w = compute_normalized_weights(p, {k: 0.0 for k in CRITERIA})
    assert set(w) == {"price", "location", "amenity", "semantic"} and abs(sum(w.values()) - 1.0) < 1e-9
    assert max(w.values()) - min(w.values()) <= 0.0001
    p_safe = UserPreferenceState(lat=10.87, lng=106.80, preferred_amenities=["ml", "safe_area"])
    w_safe = compute_normalized_weights(p_safe, {k: 0.0 for k in CRITERIA})
    assert set(w_safe) == set(CRITERIA) and abs(sum(w_safe.values()) - 1.0) < 1e-9
    w2 = compute_normalized_weights(p, {**{k: 1.0 for k in CRITERIA}, "price": -5.0})
    assert w2["price"] == 0.0 and abs(sum(w2.values()) - 1.0) < 1e-9


def test_custom_base_weights():
    w = compute_normalized_weights(_pref(False, False), {k: 1.0 for k in CRITERIA}, base_weights={"price": 2.0, "safety": 1.0, "semantic": 1.0})
    assert w["price"] == 0.5


def test_equal_split_three_criteria_sums_to_one():
    """Lỗi cũ: nhánh total<=0 trả 3 x 0.3333 = 0.9999."""
    w = compute_normalized_weights(_pref(False, False), {k: 0.0 for k in CRITERIA})
    assert abs(sum(w.values()) - 1.0) < 1e-9
