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

    # Case-insensitive / whitespace stripped match ('AIRCON' -> 'aircon', ' window_balcony ' -> 'window_balcony')
    fit_case = _amenity_fit(None, concept_scores, preferred=["AIRCON", " window_balcony "])
    assert fit_case == pytest.approx(0.7 * 1.0 + 0.3 * 0.8)

    # Negative match in preferred: (0.0 + 1.0) / 2 = 0.5 -> 0.7 * 0.5 + 0.3 * 0.8 = 0.59
    fit_negative = _amenity_fit(None, concept_scores, preferred=["pet_allowed", "aircon"])
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
    w_mandatory = _dynamic_weights({"amenities": ["aircon"]}, DEFAULT_WEIGHTS)
    assert "amenity" not in w_mandatory
    assert set(w_mandatory.keys()) == {"price", "safety", "semantic"}
    assert round(sum(w_mandatory.values()), 5) == 1.0

    # Preferred amenities requested -> amenity active
    w_pref = _dynamic_weights({"preferred_amenities": ["aircon"]}, DEFAULT_WEIGHTS)
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
    user_pref = {"preferred_amenities": ["aircon"]}
    results = rerank(candidates, user_pref=user_pref)

    assert len(results) == 2
    top_breakdown, top_item = results[0]
    assert top_item["id"] == "room_1"
    assert top_breakdown["parts"]["amenity"] == pytest.approx(0.7 * 1.0 + 0.3 * 0.9)

    explanation = explain_match(top_breakdown)
    assert "top_factors" in explanation


def test_canonical_amenities_and_partial_weights():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 1.0,
        "pet_allowed": 1.0,
        "amenity_overall": 1.0,
    }
    # Canonical taxonomy codes ('aircon', 'mezzanine', 'pet_allowed')
    fit = _amenity_fit(None, concept_scores, preferred=["aircon", "mezzanine", "pet_allowed"])
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


def test_amenity_fit_deduplicates_preferred_amenities():
    concept_scores = {
        "aircon": 1.0,
        "mezzanine": 0.0,
        "amenity_overall": 0.5,
    }
    # Passing duplicate 'aircon' in preferred must not double-count aircon:
    # unique normalized codes are ['aircon', 'mezzanine'] -> pref_fit = (1.0 + 0.0) / 2 = 0.5
    # blended with amenity_overall (0.5): 0.7 * 0.5 + 0.3 * 0.5 = 0.5
    fit = _amenity_fit(None, concept_scores, preferred=["aircon", "aircon", "mezzanine"])
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


def test_location_fit_non_linear_and_default_weights():
    from app.services.reranker import _location_fit, _location_part

    # 1. Kiểm tra DEFAULT_WEIGHTS chuẩn 5 tiêu chí mới
    assert DEFAULT_WEIGHTS["location"] == 0.25
    assert DEFAULT_WEIGHTS["price"] == 0.25
    assert DEFAULT_WEIGHTS["safety"] == 0.20
    assert DEFAULT_WEIGHTS["amenity"] == 0.20
    assert DEFAULT_WEIGHTS["semantic"] == 0.10
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    # 2. Kiểm tra _location_fit phi tuyến
    assert _location_fit(0.5, near_km=0.8, far_km=5.0) == 1.0
    assert _location_fit(0.8, near_km=0.8, far_km=5.0) == 1.0
    assert _location_fit(5.0, near_km=0.8, far_km=5.0) == 0.0
    assert _location_fit(6.0, near_km=0.8, far_km=5.0) == 0.0

    # Tại trung điểm (ratio = 0.5): 1 - 0.5^1.5 ≈ 0.6464 > 0.5 (ưu tiên vị trí gần hơn mô hình tuyến tính)
    mid_dist = 0.8 + (5.0 - 0.8) * 0.5  # 2.9 km
    assert _location_fit(mid_dist, near_km=0.8, far_km=5.0) == pytest.approx(1.0 - (0.5 ** 1.5))

    # 3. Kiểm tra _location_part với max_distance_km tùy chỉnh từ user_pref
    listing = {"listing": {"lat": 10.87, "lng": 106.80}}
    pref = {"lat": 10.87, "lng": 106.80, "max_distance_km": 3.0}
    # Cùng tọa độ -> khoảng cách ~ 0 -> score 1.0
    assert _location_part(listing, pref) == 1.0


def test_price_fit_cheapest_mode_and_excluded_room_types():
    from app.services.reranker import _price_fit
    from app.schemas.listing import VectorSearchBody

    # Căn rẻ: giá 2tr, ML score 0.40
    cheap_room = {"price_vnd": 2_000_000, "price_score": 0.40}
    # Căn đắt hơn: giá 3.8tr, ML score 0.90 (deal rất hời theo ML)
    expensive_good_deal = {"price_vnd": 3_800_000, "price_score": 0.90}

    # Ngân sách trần 4tr
    pref_normal = {"max_price": 4_000_000}
    pref_cheapest = {"max_price": 4_000_000, "prefer_cheapest": True}

    # Ở chế độ bình thường (weights price = 0.25):
    score_cheap_normal = _price_fit(cheap_room, pref_normal, weights={"price": 0.25})
    score_exp_normal = _price_fit(expensive_good_deal, pref_normal, weights={"price": 0.25})
    # Căn đắt deal hời vẫn có điểm ML kéo lại
    assert score_exp_normal > 0.45

    # Ở chế độ ưu tiên giá rẻ (weights price = 0.40 hoặc prefer_cheapest=True):
    score_cheap_priority = _price_fit(cheap_room, pref_cheapest, weights={"price": 0.40})
    score_exp_priority = _price_fit(expensive_good_deal, pref_cheapest, weights={"price": 0.40})

    # Căn rẻ 2tr (tiết kiệm 50% ngân sách) PHẢI thắng áp đảo căn 3.8tr (chỉ tiết kiệm 5%)
    assert score_cheap_priority > score_exp_priority
    assert score_cheap_priority - score_exp_priority > 0.15

    # Kiểm tra VectorSearchBody nhận excluded_room_types hợp lệ
    body = VectorSearchBody(
        query="tìm phòng trọ",
        excluded_room_types=["SLEEPBOX", 4],
    )
    assert body.excluded_room_types == ["SLEEPBOX", 4]
