"""Unit tests for backend rerank and amenity fit (Phương án 3 - Hybrid Clean Architecture)."""
import pytest
from app.services.reranker import (
    DEFAULT_WEIGHTS,
    _amenity_fit,
    _dynamic_weights,
    explain_match,
    rerank,
)


def test_amenity_fit_preferred_and_ignores_mandatory():
    concept_scores = {
        "private_wc": 1.0,
        "aircon": 1.0,
        "mezzanine": 1.0,
        "window_balcony": 1.0,
        "pet_allowed": 0.0,
        "amenity_overall": 0.8,
    }

    # Preferred canonical match (70% preferred + 30% overall)
    fit_canonical = _amenity_fit(None, concept_scores, preferred=["aircon", "window_balcony"])
    assert fit_canonical == pytest.approx(0.7 * 1.0 + 0.3 * 0.8)

    # Alias match ('ac' -> 'aircon', 'ban_cong' -> 'window_balcony')
    fit_alias = _amenity_fit(None, concept_scores, preferred=["ac", "ban_cong"])
    assert fit_alias == pytest.approx(0.7 * 1.0 + 0.3 * 0.8)

    # Negative match in preferred: (0.0 + 1.0) / 2 = 0.5 -> 0.7 * 0.5 + 0.3 * 0.8 = 0.59
    fit_negative = _amenity_fit(None, concept_scores, preferred=["pet", "aircon"])
    assert fit_negative == pytest.approx(0.7 * 0.5 + 0.3 * 0.8)

    # Mandatory (requested) is ignored in _amenity_fit (already hard-filtered at SQL & Grounding)
    fit_with_mandatory = _amenity_fit(["pet_allowed"], concept_scores, preferred=["aircon"])
    assert fit_with_mandatory == pytest.approx(0.7 * 1.0 + 0.3 * 0.8)

    # AmenityCode Enum instance match
    from app.schemas.listing import AmenityCode
    fit_enum_pref = _amenity_fit(None, concept_scores, preferred=[AmenityCode.AIRCON])
    assert fit_enum_pref == pytest.approx(0.7 * 1.0 + 0.3 * 0.8)


def test_amenity_fit_fallback_overall():
    concept_scores = {
        "amenity_overall": 0.75,
    }
    # No preferred amenities -> falls back to amenity_overall (even if mandatory requested is passed)
    assert _amenity_fit(None, concept_scores) == 0.75
    assert _amenity_fit(["aircon"], concept_scores) == 0.75

    # Completely empty concept scores -> falls back to neutral 1.0
    assert _amenity_fit(None, {}) == 1.0


def test_dynamic_weights():
    # Only price, safety, semantic active when no coords and no preferred amenities
    w_basic = _dynamic_weights({}, DEFAULT_WEIGHTS)
    assert set(w_basic.keys()) == {"price", "safety", "semantic"}
    assert round(sum(w_basic.values()), 5) == 1.0

    # Mandatory amenities alone -> amenity is NOT active in MCDM (already hard-filtered)
    w_mandatory = _dynamic_weights({"amenities": ["ac"]}, DEFAULT_WEIGHTS)
    assert "amenity" not in w_mandatory
    assert set(w_mandatory.keys()) == {"price", "safety", "semantic"}
    assert round(sum(w_mandatory.values()), 5) == 1.0

    # Preferred amenities requested -> amenity active
    w_pref = _dynamic_weights({"preferred_amenities": ["ac"]}, DEFAULT_WEIGHTS)
    assert "amenity" in w_pref
    assert round(sum(w_pref.values()), 5) == 1.0

    # AI Agent passes explicit amenity weight (e.g., user emphasized 'full nội thất') -> amenity active
    w_explicit = _dynamic_weights({}, {"price": 0.25, "safety": 0.25, "semantic": 0.25, "amenity": 0.25})
    assert "amenity" in w_explicit
    assert round(sum(w_explicit.values()), 5) == 1.0

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

    # User prefers aircon
    user_pref = {"preferred_amenities": ["may_lanh"]}
    results = rerank(candidates, user_pref=user_pref)

    assert len(results) == 2
    top_breakdown, top_item = results[0]
    assert top_item["id"] == "room_1"
    assert top_breakdown["parts"]["amenity"] == pytest.approx(0.7 * 1.0 + 0.3 * 0.9)

    explanation = explain_match(top_breakdown)
    assert "top_factors" in explanation


def test_vietnamese_diacritic_amenities_and_partial_weights():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 1.0,
        "pet_allowed": 1.0,
        "amenity_overall": 1.0,
    }
    # Tiếng Việt có dấu từ AI Agent ('máy lạnh', 'gác lửng', 'nuôi mèo')
    fit = _amenity_fit(None, concept_scores, preferred=["máy lạnh", "gác lửng", "nuôi mèo"])
    assert fit == 1.0


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
    assert res.room_type.id == 1


def test_amenity_fit_deduplicates_canonical_and_vietnamese_aliases():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 0.0,
        "amenity_overall": 0.5,
    }
    # Passing both 'aircon' and 'máy lạnh' in preferred must not double-count aircon:
    # unique normalized codes are ['aircon', 'mezzanine'] -> pref_fit = (1.0 + 0.0) / 2 = 0.5
    # blended with amenity_overall (0.5): 0.7 * 0.5 + 0.3 * 0.5 = 0.5
    fit = _amenity_fit(None, concept_scores, preferred=["aircon", "máy lạnh", "mezzanine"])
    assert fit == pytest.approx(0.5)


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
    body = VectorSearchBody(
        query="phòng trọ gần thủ đức",
        amenities=["aircon", "mezzanine"],
        room_type="STUDIO",
        min_price=2000000,
        max_price=4000000,
        min_area=15,
        max_area=30,
    )
    assert body.query == "phòng trọ gần thủ đức"
    assert body.amenities == ["aircon", "mezzanine"]
    assert body.room_type == "STUDIO"
    assert body.room_type_id == 2  # Tự động map STUDIO -> ID 2

    # Test VectorSearchBody validation: min_price > max_price
    with pytest.raises(ValueError, match="min_price không được lớn hơn max_price"):
        VectorSearchBody(query="phòng trọ", min_price=5000000, max_price=2000000)

    # Test VectorSearchBody validation: min_area > max_area
    with pytest.raises(ValueError, match="min_area không được lớn hơn max_area"):
        VectorSearchBody(query="phòng trọ", min_area=30, max_area=15)

    # Test VectorSearchBody validation: invalid room_type
    with pytest.raises(ValueError, match="room_type 'BIET_THU' không hợp lệ"):
        VectorSearchBody(query="phòng trọ", room_type="BIET_THU")

    # Test ListingIdsRequest
    ids_req = ListingIdsRequest(ids=["nhatot_1", "nhatot_2"])
    assert len(ids_req.ids) == 2
