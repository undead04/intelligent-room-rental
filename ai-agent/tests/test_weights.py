import itertools
import random

import pytest

from intelligence.intent_weights import compute_normalized_weights, detect_intent_multipliers
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
    assert set(compute_normalized_weights(_pref(False, False), ones)) == {"price", "safety", "semantic"}
    assert set(compute_normalized_weights(_pref(True, False), ones)) == {"price", "safety", "semantic", "location"}
    assert set(compute_normalized_weights(_pref(False, True), ones)) == {"price", "safety", "semantic", "amenity"}
    assert set(compute_normalized_weights(_pref(True, True), ones)) == set(CRITERIA)


def test_mandatory_amenities_alone_do_not_enable_amenity_weight():
    p = UserPreferenceState(amenities=["aircon", "no_shared_landlord"])
    w = compute_normalized_weights(p, {k: 1.0 for k in CRITERIA})
    assert "amenity" not in w


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
    assert set(w) == set(CRITERIA) and abs(sum(w.values()) - 1.0) < 1e-9
    assert max(w.values()) - min(w.values()) <= 0.0001
    w2 = compute_normalized_weights(p, {**{k: 1.0 for k in CRITERIA}, "price": -5.0})
    assert w2["price"] == 0.0 and abs(sum(w2.values()) - 1.0) < 1e-9


def test_custom_base_weights():
    w = compute_normalized_weights(_pref(False, False), {k: 1.0 for k in CRITERIA}, base_weights={"price": 2.0, "safety": 1.0, "semantic": 1.0})
    assert w["price"] == 0.5


def test_fallback_detector_still_works_and_no_longer_leaks_boost_numbers():
    m, expl = detect_intent_multipliers("Tìm phòng giá rẻ gần UIT")
    assert m["price"] == 2.0 and m["location"] == 2.0
    assert expl and not any("boost" in e or "x)" in e for e in expl)
    m2, _ = detect_intent_multipliers("tìm phòng", {"price": 2.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0})
    assert m2["price"] == 2.0          # hành vi cũ (chỉ tăng, không giảm) - sẽ được thay ở bước nlu


def test_equal_split_three_criteria_sums_to_one():
    """Lỗi cũ: nhánh total<=0 trả 3 x 0.3333 = 0.9999."""
    w = compute_normalized_weights(_pref(False, False), {k: 0.0 for k in CRITERIA})
    assert abs(sum(w.values()) - 1.0) < 1e-9
