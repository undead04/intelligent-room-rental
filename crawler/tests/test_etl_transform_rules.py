"""Black-box unit tests cho các business rules mới trong ListingTransformer:
1. Auto-fill furnishing_code = 2 (Nội thất đầy đủ) khi furnishing_code hiện tại là None và LLM phát hiện có nội thất.
2. Ép phân loại SLEEPBOX (room_type_id = 4) khi 0 < price_vnd < 1_000_000.
3. Thứ tự tính safety_score & amenity_overall v2 sau Bước 8.5/9 (dùng raw_furnishing_code gốc, room_type đã chốt).
4. DataLoader bảo toàn price_score cũ trong DB khi đầu vào price_score=None.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock, patch

from crawler.etl.db_models import Listing as CrawlerListing
from crawler.etl.load import DataLoader
from crawler.etl.transform import ListingTransformer


def _make_base_raw(**overrides) -> dict:
    base = {
        "listing_id": "nhatot_99001",
        "source": "nhatot",
        "title": "Phòng trọ sinh viên gần ĐHQG",
        "description": "Phòng sạch sẽ thoáng mát, giờ giấc tự do.",
        "price_vnd": 2_500_000,
        "area_m2": 20.0,
        "city": "TP.HCM",
        "district": "Thủ Đức",
        "ward": "Linh Trung",
        "furnishing_code": None,
        "room_type": "ROOM",
        "is_active": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Nhóm 1: Happy Path
# ---------------------------------------------------------------------------

def test_autofill_furnishing_code_when_none_and_llm_has_furniture():
    """Khi furnishing_code=None và LLM báo cáo furniture='yes' -> fill bằng 2 (Nội thất đầy đủ)."""
    transformer = ListingTransformer()
    raw = _make_base_raw(furnishing_code=None)
    llm_report = {
        "room_type": "ROOM",
        "amenities": {
            "furniture": {"value": "yes", "evidence": "có giường tủ đầy đủ"},
        },
    }

    cleaned = transformer.clean_record(raw, report=llm_report)
    assert cleaned["furnishing_code"] == 2


def test_sub_million_price_forces_sleepbox_even_if_llm_or_raw_says_room():
    """Khi 0 < price_vnd < 1_000_000 -> ép chắc chắn SLEEPBOX (room_type_id=4)."""
    transformer = ListingTransformer()
    raw = _make_base_raw(price_vnd=850_000, room_type="ROOM")
    llm_report = {"room_type": "ROOM"}

    cleaned = transformer.clean_record(raw, report=llm_report)
    assert cleaned["room_type"] == "SLEEPBOX"
    assert cleaned["room_type_id"] == 4
    assert "Ký túc xá" in cleaned["embedding_text"] or "Sleepbox" in cleaned["embedding_text"]


# ---------------------------------------------------------------------------
# Nhóm 2: Boundary & Edge Cases
# ---------------------------------------------------------------------------

def test_do_not_overwrite_existing_furnishing_code():
    """Nếu furnishing_code đã có giá trị (ví dụ 2 hoặc 3) -> giữ nguyên, không ghi đè."""
    transformer = ListingTransformer()
    llm_report = {
        "amenities": {
            "furniture": {"value": "yes", "evidence": "có bàn ghế"},
        },
    }

    for existing_code in (1, 2, 3):
        raw = _make_base_raw(furnishing_code=existing_code)
        cleaned = transformer.clean_record(raw, report=llm_report)
        assert cleaned["furnishing_code"] == existing_code


def test_furnishing_remains_none_when_llm_unknown_or_no():
    """Khi LLM trả furniture='unknown' hoặc 'no' -> furnishing_code vẫn giữ None."""
    transformer = ListingTransformer()
    for val in ("unknown", "no"):
        raw = _make_base_raw(furnishing_code=None)
        cleaned = transformer.clean_record(
            raw,
            report={"amenities": {"furniture": {"value": val, "evidence": ""}}},
        )
        assert cleaned["furnishing_code"] is None


def test_price_boundary_999999_vs_1000000_vs_0():
    """Kiểm tra biên 999_999 (<1tr -> SLEEPBOX), 1_000_000 (giữ ROOM), 0 (không ép)."""
    transformer = ListingTransformer()

    below = transformer.clean_record(_make_base_raw(price_vnd=999_999, room_type="ROOM"))
    assert below["room_type"] == "SLEEPBOX"
    assert below["room_type_id"] == 4

    exact = transformer.clean_record(_make_base_raw(price_vnd=1_000_000, room_type="ROOM"))
    assert exact["room_type"] == "ROOM"
    assert exact["room_type_id"] == 1

    zero = transformer.clean_record(_make_base_raw(price_vnd=0, room_type="ROOM"))
    assert zero["room_type"] == "ROOM"
    assert zero["room_type_id"] == 1


# ---------------------------------------------------------------------------
# Nhóm 3: State Mutation & Input Isolation
# ---------------------------------------------------------------------------

def test_clean_record_does_not_mutate_input_dict():
    """clean_record không được làm biến đổi dict đầu vào của caller."""
    transformer = ListingTransformer()
    raw = _make_base_raw(price_vnd=700_000, furnishing_code=None)
    snapshot = copy.deepcopy(raw)
    llm_report = {
        "amenities": {"furniture": {"value": "yes", "evidence": "giường tầng có sẵn nệm"}}
    }

    cleaned = transformer.clean_record(raw, report=llm_report)
    assert raw == snapshot
    assert cleaned["furnishing_code"] == 2
    assert cleaned["room_type"] == "SLEEPBOX"


# ---------------------------------------------------------------------------
# Nhóm 4: Persistence / Schema Compatibility
# ---------------------------------------------------------------------------

def test_autofill_furnishing_from_concept_scores_fallback():
    """Nếu record đã mang concept_scores (khi không có report raw) -> vẫn fill furnishing_code=2."""
    transformer = ListingTransformer()
    raw = _make_base_raw(
        furnishing_code=None,
        concept_scores={"amenities": {"furniture": 1.0}, "safety": {}},
    )

    cleaned = transformer.clean_record(raw)
    assert cleaned["furnishing_code"] == 2


def test_v2_scoring_uses_raw_furnishing_and_final_room_type():
    """Bước 8.5 auto-fill furnishing_code=2 không tạo sàn 80% ảo; tin <1tr ép SLEEPBOX chấm theo SLEEPBOX."""
    transformer = ListingTransformer()

    # 1. Phòng trọ có furnishing_code=None, chỉ nhắc có giường tủ -> auto-fill 2, nhưng amenity_overall chỉ cộng đúng furniture (12đ = 0.12)
    raw_room = _make_base_raw(
        furnishing_code=None,
        description="Phòng trọ có giường tủ.",
        room_type="ROOM",
    )
    cleaned_room = transformer.clean_record(
        raw_room,
        report={"room_type": "ROOM", "amenities": {"furniture": {"value": "yes", "evidence": "giường tủ"}}},
    )
    assert cleaned_room["furnishing_code"] == 2
    assert cleaned_room["amenity_overall"] == 0.12
    assert cleaned_room["safety_score"] == 0.30

    # 2. Tin < 1tr ép từ ROOM -> SLEEPBOX ở Bước 9 phải chấm safety_score baseline SLEEPBOX (0.26)
    raw_cheap = _make_base_raw(price_vnd=850_000, room_type="ROOM", description="Phòng giá rẻ.")
    cleaned_cheap = transformer.clean_record(raw_cheap, report={"room_type": "ROOM"})
    assert cleaned_cheap["room_type"] == "SLEEPBOX"
    assert cleaned_cheap["safety_score"] == 0.26


def test_dataloader_preserves_existing_price_score_when_incoming_is_none():
    """DataLoader không ghi đè mất price_score cũ trong DB khi record transform có price_score=None."""
    existing_listing = MagicMock()
    existing_listing.price_score = 0.82

    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = MagicMock()
    engine.connect.return_value.__exit__.return_value = False

    session = MagicMock()
    session.get.side_effect = lambda model, key: existing_listing if model is CrawlerListing else MagicMock()

    loader = DataLoader()
    with (
        patch("crawler.etl.load.create_db_session", return_value=(engine, session)),
        patch("crawler.etl.load.Base.metadata.create_all"),
    ):
        loader.load_to_postgres(
            [
                {
                    "id": "nhatot_preserve_1",
                    "title": "Phòng test giữ price_score",
                    "price_vnd": 4_500_000,
                    "area_m2": 25.0,
                    "room_type": "ROOM",
                    "room_type_id": 1,
                    "price_score": None,
                    "safety_score": 0.55,
                    "amenity_overall": 0.72,
                }
            ]
        )

    assert existing_listing.price_score == 0.82
    assert existing_listing.safety_score == 0.55
    assert existing_listing.amenity_overall == 0.72


def test_transform_rejects_zero_area_zero_price_oor_geo_and_extreme_bounds():
    """Transform phải loại bỏ tin thiếu diện tích, thiếu giá, tọa độ ngoài VN hoặc diện tích/đơn giá ảo."""
    transformer = ListingTransformer(enable_price_evaluator=False)
    items = [
        {
            "listing_id": "ok_room",
            "title": "Phòng trọ thoáng mát",
            "price_vnd": 3_500_000,
            "area_m2": 22.0,
            "lat": 10.77,
            "lng": 106.69,
            "room_type": "ROOM",
        },
        {
            "listing_id": "bad_zero_area",
            "title": "Có giá nhưng thiếu diện tích",
            "price_vnd": 3_500_000,
            "area_m2": 0.0,
            "lat": 10.77,
            "lng": 106.69,
            "room_type": "ROOM",
        },
        {
            "listing_id": "bad_zero_price",
            "title": "Có diện tích nhưng thiếu giá",
            "price_vnd": 0.0,
            "area_m2": 25.0,
            "lat": 10.77,
            "lng": 106.69,
            "room_type": "ROOM",
        },
        {
            "listing_id": "bad_oor_geo",
            "title": "Tọa độ 0,0 ngoài Việt Nam",
            "price_vnd": 3_500_000,
            "area_m2": 25.0,
            "lat": 0.0,
            "lng": 0.0,
            "room_type": "ROOM",
        },
        {
            "listing_id": "bad_area_2000",
            "title": "Diện tích ảo 2000m2",
            "price_vnd": 5_400_000,
            "area_m2": 2000.0,
            "lat": 10.77,
            "lng": 106.69,
            "room_type": "ROOM",
        },
    ]

    cleans = transformer.transform(items)
    assert [c["listing_id"] for c in cleans] == ["ok_room"]
