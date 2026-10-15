"""Unit tests for crawler/schema/listing.py and crawler/schema/enum.py."""
import pytest
from crawler.schema.enum import AmenityCode, RoomType
from crawler.schema.listing import (
    Amenities,
    ListingExtraction,
    Numeric,
    Rules,
    Safety,
    Signal,
)


def test_signal_score_and_validation():
    # Unknown signal has no evidence
    sig_unknown = Signal(value="unknown", evidence="some text")
    assert sig_unknown.value == "unknown"
    assert sig_unknown.evidence is None
    assert sig_unknown.score() == 0.4

    # Yes signal preserves evidence
    sig_yes = Signal(value="yes", evidence="WC riêng")
    assert sig_yes.value == "yes"
    assert sig_yes.evidence == "WC riêng"
    assert sig_yes.score() == 1.0

    # No signal
    sig_no = Signal(value="no", evidence="WC chung")
    assert sig_no.value == "no"
    assert sig_no.score() == 0.0


def test_amenity_overall_score_calculation():
    # 1. Empty room -> 0.0
    extraction = ListingExtraction()
    assert extraction.amenity_overall_score() == 0.0

    # 2. Add private_wc (20 pts) -> 0.20
    extraction.amenities.private_wc = Signal(value="yes", evidence="wc rieng")
    assert extraction.amenity_overall_score() == 0.20

    # 3. Add aircon (20 pts) -> 0.40
    extraction.amenities.aircon = Signal(value="yes", evidence="may lanh")
    assert extraction.amenity_overall_score() == 0.40

    # 4. Add mezzanine (15 pts) + kitchen (15 pts) -> 0.70
    extraction.amenities.mezzanine = Signal(value="yes", evidence="gac lung")
    extraction.amenities.kitchen = Signal(value="yes", evidence="ke bep")
    assert extraction.amenity_overall_score() == 0.70

    # 5. Add fridge (10 pts) + washing_machine (10 pts) + window_balcony (10 pts) -> 1.0
    extraction.amenities.fridge = Signal(value="yes", evidence="tu lanh")
    extraction.amenities.washing_machine = Signal(value="yes", evidence="may giat")
    extraction.amenities.window_balcony = Signal(value="yes", evidence="ban cong")
    assert extraction.amenity_overall_score() == 1.00

    # 6. Additional amenities still capped at 1.0
    extraction.amenities.elevator = Signal(value="yes", evidence="thang may")
    extraction.amenities.parking = Signal(value="yes", evidence="ham de xe")
    assert extraction.amenity_overall_score() == 1.00


def test_safety_score_calculation():
    extraction = ListingExtraction()
    # All unknown -> 0.4
    assert extraction.safety_score() == 0.40

    # Camera (0.30) and Guard (0.30) yes -> 0.3*1.0 + 0.3*1.0 + 0.25*0.4 + 0.15*0.4 = 0.76
    extraction.safety.camera = Signal(value="yes", evidence="camera")
    extraction.safety.guard = Signal(value="yes", evidence="bao ve")
    assert extraction.safety_score() == 0.76


def test_verify_evidence_anti_hallucination():
    source_text = "Phòng trọ có máy lạnh Daikin, WC riêng khép kín, ban công thoáng mát."

    extraction = ListingExtraction(
        amenities=Amenities(
            aircon=Signal(value="yes", evidence="máy lạnh"),
            private_wc=Signal(value="yes", evidence="WC riêng"),
            window_balcony=Signal(value="yes", evidence="ban công thoáng mát"),
            fridge=Signal(value="yes", evidence="tủ lạnh Side-by-Side"),  # Hallucinated!
        ),
        rules=Rules(
            pet_allowed=Signal(value="yes", evidence="cho nuôi chó mèo"),  # Hallucinated!
        ),
        safety=Safety(
            guard=Signal(value="yes", evidence="bảo vệ 24/7"),  # Hallucinated!
        ),
    )

    verified = extraction.verify_evidence(source_text)

    # Valid signals are kept
    assert verified.amenities.aircon.value == "yes"
    assert verified.amenities.private_wc.value == "yes"
    assert verified.amenities.window_balcony.value == "yes"

    # Hallucinated signals are downgraded to unknown
    assert verified.amenities.fridge.value == "unknown"
    assert verified.amenities.fridge.evidence is None
    assert verified.rules.pet_allowed.value == "unknown"
    assert verified.safety.guard.value == "unknown"


def test_to_concept_scores():
    extraction = ListingExtraction()
    extraction.amenities.private_wc = Signal(value="yes", evidence="wc rieng")
    extraction.rules.pet_allowed = Signal(value="yes", evidence="nuoi pet")
    extraction.safety.camera = Signal(value="yes", evidence="camera")

    scores = extraction.to_concept_scores()

    assert scores["private_wc"] == 1.0
    assert scores["pet_allowed"] == 1.0
    assert scores["camera"] == 1.0
    assert scores["aircon"] == 0.4  # default unknown
    assert "amenity_overall" in scores
    assert "safety_overall" in scores
    assert scores["amenity_overall"] == 0.20


def test_amenity_code_normalization():
    assert AmenityCode.normalize("ac") == "aircon"
    assert AmenityCode.normalize("may_lanh") == "aircon"
    assert AmenityCode.normalize("dieu_hoa") == "aircon"
    assert AmenityCode.normalize("wc") == "private_wc"
    assert AmenityCode.normalize("ve_sinh_rieng") == "private_wc"
    assert AmenityCode.normalize("gac") == "mezzanine"
    assert AmenityCode.normalize("ban_cong") == "window_balcony"
    assert AmenityCode.normalize("pet") == "pet_allowed"
    assert AmenityCode.normalize("khoa_van_tay") == "fingerprint_lock"
    assert AmenityCode.normalize("the_tu") == "fingerprint_lock"
    assert AmenityCode.normalize("unknown_code_123") == "unknown_code_123"
    assert AmenityCode.normalize("") is None
