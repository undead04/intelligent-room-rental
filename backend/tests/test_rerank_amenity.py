"""Unit tests for backend rerank and amenity fit."""
import pytest
from app.utils.utils import (
    _amenity_fit,
    _dynamic_weights,
    DEFAULT_WEIGHTS,
    rerank,
    explain_match,
)


def test_amenity_fit_canonical_and_aliases():
    concept_scores = {
        "private_wc": 1.0,
        "aircon": 1.0,
        "mezzanine": 1.0,
        "window_balcony": 1.0,
        "pet_allowed": 0.0,
        "amenity_overall": 0.8,
    }

    # Canonical match
    fit_canonical = _amenity_fit(["aircon", "window_balcony"], concept_scores)
    assert fit_canonical == 1.0

    # Alias match ('ac' -> 'aircon', 'ban_cong' -> 'window_balcony')
    fit_alias = _amenity_fit(["ac", "ban_cong"], concept_scores)
    assert fit_alias == 1.0

    # Negative match
    fit_negative = _amenity_fit(["pet", "aircon"], concept_scores)
    assert fit_negative == 0.5  # (0.0 + 1.0) / 2


def test_amenity_fit_fallback_overall():
    concept_scores = {
        "amenity_overall": 0.75,
    }
    # No amenities requested -> falls back to amenity_overall
    assert _amenity_fit(None, concept_scores) == 0.75
    assert _amenity_fit([], concept_scores) == 0.75

    # Completely empty concept scores -> falls back to neutral 1.0
    assert _amenity_fit(None, {}) == 1.0


def test_dynamic_weights():
    # Only price, safety, semantic active when no coords and no amenities
    w_basic = _dynamic_weights({}, DEFAULT_WEIGHTS)
    assert set(w_basic.keys()) == {"price", "safety", "semantic"}
    assert round(sum(w_basic.values()), 5) == 1.0

    # Amenities requested -> amenity active
    w_amenities = _dynamic_weights({"amenities": ["ac"]}, DEFAULT_WEIGHTS)
    assert "amenity" in w_amenities
    assert round(sum(w_amenities.values()), 5) == 1.0

    # Location provided -> location active
    w_loc = _dynamic_weights({"lat": 10.8, "lng": 106.7}, DEFAULT_WEIGHTS)
    assert "location" in w_loc
    assert "amenity" not in w_loc

    # include_amenity_overall requested -> amenity active
    w_overall = _dynamic_weights({"include_amenity_overall": True}, DEFAULT_WEIGHTS)
    assert "amenity" in w_overall


def test_rerank_with_candidates():
    candidates = [
        {
            "id": "room_1",
            "listing": {
                "price_score": 0.9,
                "safety_score": 0.8,
                "concept_scores": {"aircon": 1.0, "private_wc": 1.0, "amenity_overall": 0.9},
                "similarity_score": 0.85,
            },
        },
        {
            "id": "room_2",
            "listing": {
                "price_score": 0.5,
                "safety_score": 0.4,
                "concept_scores": {"aircon": 0.0, "private_wc": 0.4, "amenity_overall": 0.2},
                "similarity_score": 0.5,
            },
        },
    ]

    # User explicitly wants aircon
    user_pref = {"amenities": ["may_lanh"]}
    results = rerank(candidates, user_pref=user_pref)

    assert len(results) == 2
    top_breakdown, top_item = results[0]
    assert top_item["id"] == "room_1"
    assert top_breakdown["parts"]["amenity"] == 1.0

    explanation = explain_match(top_breakdown)
    assert "top_factors" in explanation
    assert explanation["score"] > 0.8
