"""Unit tests for backend rerank and amenity fit."""
import pytest
from app.services.reranker import (
    DEFAULT_WEIGHTS,
    _amenity_fit,
    _dynamic_weights,
    explain_match,
    rerank,
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


def test_vietnamese_diacritic_amenities_and_partial_weights():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 1.0,
        "pet_allowed": 1.0,
    }
    # Tiếng Việt có dấu từ AI Agent ('máy lạnh', 'gác lửng', 'nuôi mèo')
    fit = _amenity_fit(["máy lạnh", "gác lửng", "nuôi mèo"], concept_scores)
    assert fit == 1.0

    # Partial weights dict missing 'amenity' or 'location' should not raise KeyError
    partial_base = {"price": 0.5, "safety": 0.25, "semantic": 0.25}
    w = _dynamic_weights({"amenities": ["máy lạnh"]}, partial_base)
    assert "amenity" in w
    assert round(sum(w.values()), 5) == 1.0


def test_room_type_reference_and_listing_response_schema():
    from app.schemas.listing import ListingResponse, RoomTypeReference

    class DummyRoomType:
        id = 1
        name = "Phòng trọ"

    rt = RoomTypeReference.model_validate(DummyRoomType())
    assert rt.id == 1
    assert rt.name == "Phòng trọ"

    listing_data = {
        "id": "nhatot_999",
        "title": "Phòng trọ Thủ Đức",
        "price_score": 0.82,
        "amenity_overall": 0.75,
        "room_type": DummyRoomType(),
    }
    res = ListingResponse.model_validate(listing_data)
    assert res.price_score == 0.82
    assert res.amenity_overall == 0.75
    assert res.room_type is not None
    assert res.room_type.name == "Phòng trọ"


def test_amenity_fit_deduplicates_canonical_and_vietnamese_aliases():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 0.0,
    }
    # Passing both 'aircon' and 'máy lạnh' must not double-count aircon:
    # unique normalized codes are ['aircon', 'mezzanine'] -> (1.0 + 0.0) / 2 = 0.5
    fit = _amenity_fit(["aircon", "máy lạnh", "mezzanine"], concept_scores)
    assert fit == 0.5


def test_build_or_tsquery_string_for_sparse_fts():
    from app.repositories.listing_repository import _build_or_tsquery_string

    q = _build_or_tsquery_string("Tìm phòng gần UIT dưới 4 triệu có máy lạnh")
    assert " | " in q
    assert "uit" in q
    assert "tìm" not in q.split(" | ")
    assert "dưới" not in q.split(" | ")


def test_listing_schemas_validation():
    from app.schemas.listing import ListingFilterParams, VectorSearchBody, ListingIdsRequest

    # Test ListingFilterParams validation
    filters = ListingFilterParams(min_price=1000000, max_price=5000000)
    assert filters.min_price == 1000000

    # Test invalid range raises ValueError
    with pytest.raises(ValueError, match="min_price không được lớn hơn max_price"):
        ListingFilterParams(min_price=5000000, max_price=1000000)

    # Test VectorSearchBody
    body = VectorSearchBody(query="phòng trọ gần thủ đức", amenities=["aircon"])
    assert body.query == "phòng trọ gần thủ đức"
    assert body.amenities == ["aircon"]

    # Test ListingIdsRequest
    ids_req = ListingIdsRequest(ids=["nhatot_1", "nhatot_2"])
    assert len(ids_req.ids) == 2



