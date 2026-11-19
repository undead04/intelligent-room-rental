"""Unit tests for crawler/schema/listing.py and crawler/schema/enum.py."""
import pytest
from crawler.schema.enums import AmenityCode, RoomType
from crawler.schema.listing import (
    Amenities,
    ListingExtraction,
    Rules,
    Safety,
    Signal,
    extract_listing_full_text,
)


def test_signal_score_and_validation():
    # Unknown signal has no evidence
    sig_unknown = Signal(value="unknown", evidence="some text")
    assert sig_unknown.value == "unknown"
    assert sig_unknown.evidence is None
    assert sig_unknown.score() == 0.0

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
    # 1. Empty ROOM -> 0.0
    extraction = ListingExtraction()
    assert extraction.amenity_overall_score() == 0.0

    # 2. Add private_wc (18 pts for ROOM) -> 0.18
    extraction.amenities.private_wc = Signal(value="yes", evidence="wc rieng")
    assert extraction.amenity_overall_score() == 0.18

    # 3. Add aircon (18 pts) -> 0.36
    extraction.amenities.aircon = Signal(value="yes", evidence="may lanh")
    assert extraction.amenity_overall_score() == 0.36

    # 4. Add mezzanine (8 pts) + kitchen (12 pts) -> 0.56
    extraction.amenities.mezzanine = Signal(value="yes", evidence="gac lung")
    extraction.amenities.kitchen = Signal(value="yes", evidence="ke bep")
    assert extraction.amenity_overall_score() == 0.56

    # 5. Add fridge (8 pts) + washing_machine (8 pts) + window_balcony (10 pts) -> 0.82
    extraction.amenities.fridge = Signal(value="yes", evidence="tu lanh")
    extraction.amenities.washing_machine = Signal(value="yes", evidence="may giat")
    extraction.amenities.window_balcony = Signal(value="yes", evidence="ban cong")
    assert extraction.amenity_overall_score() == 0.82

    # 6. Add furniture (12 pts) + parking (6 pts) -> 1.00, bonus elevator capped at 1.00
    extraction.amenities.furniture = Signal(value="yes", evidence="giuong tu")
    extraction.amenities.parking = Signal(value="yes", evidence="cho de xe")
    assert extraction.amenity_overall_score() == 1.00
    extraction.amenities.elevator = Signal(value="yes", evidence="thang may")
    assert extraction.amenity_overall_score() == 1.00


def test_safety_score_calculation():
    # 1. Baseline phân biệt nhẹ theo loại phòng khi không có bằng chứng
    assert ListingExtraction(room_type=RoomType.SLEEPBOX).safety_score() == 0.26
    assert ListingExtraction(room_type=RoomType.ROOM).safety_score() == 0.30
    assert ListingExtraction(room_type=RoomType.STUDIO).safety_score() == 0.34
    assert ListingExtraction(room_type=RoomType.WHOLE_HOUSE).safety_score() == 0.36
    assert ListingExtraction(room_type=RoomType.APARTMENT).safety_score() == 0.40

    # 2. ROOM có camera + fingerprint_lock -> vươn qua ngưỡng 0.70 (công bằng với chung cư)
    extraction = ListingExtraction(room_type=RoomType.ROOM)
    extraction.safety.camera = Signal(value="yes", evidence="camera")
    extraction.safety.fingerprint_lock = Signal(value="yes", evidence="van tay")
    assert extraction.safety_score() >= 0.70
    assert extraction.safety_score() <= 1.00


def test_v2_scoring_respects_explicit_no_and_furnishing_floor():
    # 1. Explicit 'no' không bao giờ bị đè bởi mặc định loại phòng hay regex thu hồi
    apt_no_elev = ListingExtraction(
        room_type=RoomType.APARTMENT,
        amenities=Amenities(elevator=Signal(value="no", evidence="thang bộ")),
    )
    apt_default = ListingExtraction(room_type=RoomType.APARTMENT)
    assert apt_no_elev.amenity_overall_score() < apt_default.amenity_overall_score()

    studio_no_wc = ListingExtraction(
        room_type=RoomType.STUDIO,
        amenities=Amenities(private_wc=Signal(value="no", evidence="wc chung")),
    )
    assert studio_no_wc.amenity_overall_score() == 0.0

    room_no_smart = ListingExtraction(
        room_type=RoomType.ROOM,
        safety=Safety(fingerprint_lock=Signal(value="no", evidence="không dùng khóa vân tay")),
    )
    assert room_no_smart.safety_score(source_text="không dùng khóa vân tay, cửa thường") == 0.30

    # 2. Thu hồi PCCC và khóa từ/lễ tân khi đang unknown giúp tăng safety_score hợp lý
    room_pccc = ListingExtraction(room_type=RoomType.ROOM)
    assert room_pccc.safety_score(source_text="Phòng có cửa khóa từ, hệ thống PCCC đạt chuẩn") == 0.68
    assert room_pccc.safety_score(source_text="Phòng có cửa khóa từ, lễ tân trực 24/7, PCCC đạt chuẩn") >= 0.70

    # 3. furnishing_code in (1, 2) cùng hưởng sàn 80% cụm thiết bị (trừ SLEEPBOX); code=3 không hưởng sàn
    studio = ListingExtraction(room_type=RoomType.STUDIO)
    s_fc1 = studio.amenity_overall_score(furnishing_code=1)
    s_fc2 = studio.amenity_overall_score(furnishing_code=2)
    s_fc3 = studio.amenity_overall_score(furnishing_code=3)
    assert s_fc1 == s_fc2 == 0.58
    assert s_fc3 == 0.15

    # Explicit 'no' cho máy giặt trên STUDIO có furnishing_code=2 -> loại máy giặt khỏi cụm 80%
    studio_no_wm = ListingExtraction(
        room_type=RoomType.STUDIO,
        amenities=Amenities(washing_machine=Signal(value="no", evidence="chưa có máy giặt")),
    )
    assert studio_no_wm.amenity_overall_score(furnishing_code=2) == 0.50

    # SLEEPBOX không áp dụng sàn 80% dù furnishing_code=1
    sleepbox_fc1 = ListingExtraction(room_type=RoomType.SLEEPBOX)
    assert sleepbox_fc1.amenity_overall_score(furnishing_code=1) == 0.14


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
    assert scores["aircon"] == 0.0  # default unknown/unconfirmed is 0.0
    assert "amenity_overall" not in scores
    assert "safety_overall" not in scores
    assert extraction.amenity_overall_score() == 0.20
    assert extraction.safety_score() == 0.57




def test_verify_evidence_reconciles_extra_amenities():
    """Kiểm tra cơ chế tự động thu hồi tiện ích chuẩn bị LLM nhầm lẫn đưa vào extra_amenities."""
    source_text = (
        "Không gian rộng, nhiều ánh sáng tự nhiên. Có bếp riêng, tủ lạnh, máy lạnh mới. "
        "Nội thất gỗ mới, gác lửng tiện nghi. Khu vực an ninh, view Landmark 81."
    )
    # Giả sử LLM bỏ sót amenities và nhét hết vào extra_amenities
    extraction = ListingExtraction(
        extra_amenities=[
            "Nhiều ánh sáng tự nhiên",
            "Nội thất gỗ mới",
            "máy lạnh mới",
            "view Landmark 81",
        ]
    )

    verified = extraction.verify_evidence(source_text)

    # Đã được tự động thu hồi về đúng nhóm chuẩn
    assert verified.amenities.aircon.value == "yes"
    assert verified.amenities.furniture.value == "yes"
    assert verified.amenities.window_balcony.value == "yes"

    # Chỉ tiện ích thực sự đặc thù mới được giữ lại trong extra_amenities
    assert verified.extra_amenities == ["view Landmark 81"]


def test_extract_listing_full_text():
    # 1. Both title and description present
    item_1 = {"title": "Phòng trọ Q10", "description": "Có gác lửng, máy lạnh"}
    assert extract_listing_full_text(item_1) == "Phòng trọ Q10\nCó gác lửng, máy lạnh"

    # 2. Title already included in description
    item_2 = {"title": "Phòng trọ Q10", "description": "Phòng trọ Q10 có gác lửng"}
    assert extract_listing_full_text(item_2) == "Phòng trọ Q10 có gác lửng"

    # 3. Only title
    item_3 = {"title": "Phòng trọ Q10 giá rẻ"}
    assert extract_listing_full_text(item_3) == "Phòng trọ Q10 giá rẻ"

    # 4. Only description
    item_4 = {"description": "Phòng có máy lạnh, WC riêng"}
    assert extract_listing_full_text(item_4) == "Phòng có máy lạnh, WC riêng"


def test_verify_evidence_tone_variations_and_bullets():
    """Kiểm tra đối soát evidence với định dạng thực tế (bullet, tab, emoji, lệch dấu thanh hoà/hòa)."""
    source_text = (
        "\t•\tCó bếp riêng, tủ lạnh, máy điều hoà mới\n"
        "\t•\tNội thất gỗ mới, gác lửng tiện nghi\n"
        "✅ Khu vực an ninh, di chuyển dễ dàng"
    )

    extraction = ListingExtraction(
        amenities=Amenities(
            # Text ghi 'điều hoà' (o + à), LLM trích 'điều hòa' (ò + a)
            aircon=Signal(value="yes", evidence="máy điều hòa"),
            kitchen=Signal(value="yes", evidence="Có bếp riêng"),
            fridge=Signal(value="yes", evidence="tủ lạnh"),
            mezzanine=Signal(value="yes", evidence="gác lửng"),
            furniture=Signal(value="yes", evidence="Nội thất gỗ mới"),
        ),
        safety=Safety(
            safe_area=Signal(value="yes", evidence="Khu vực an ninh"),
        ),
    )

    verified = extraction.verify_evidence(source_text)
    assert verified.amenities.aircon.value == "yes"
    assert verified.amenities.kitchen.value == "yes"
    assert verified.amenities.fridge.value == "yes"
    assert verified.amenities.mezzanine.value == "yes"
    assert verified.amenities.furniture.value == "yes"
    assert verified.safety.safe_area.value == "yes"


def test_verify_evidence_from_title():
    """Kiểm tra tiện ích nằm trên tiêu đề được giữ lại thành công khi hợp nhất text."""
    raw_item = {
        "title": "Phòng gác lửng xinh xắn – đầy đủ nội thất, dọn vào ở ngay",
        "description": "Giờ giấc tự do, không chung chủ, liên hệ 090xxx để xem phòng."
    }
    source_text = extract_listing_full_text(raw_item)

    extraction = ListingExtraction(
        amenities=Amenities(
            mezzanine=Signal(value="yes", evidence="gác lửng"),
            furniture=Signal(value="yes", evidence="đầy đủ nội thất"),
        ),
        rules=Rules(
            free_hours=Signal(value="yes", evidence="Giờ giấc tự do"),
            no_shared_landlord=Signal(value="yes", evidence="không chung chủ"),
        ),
    )

    verified = extraction.verify_evidence(source_text)
    assert verified.amenities.mezzanine.value == "yes"
    assert verified.amenities.furniture.value == "yes"
    assert verified.rules.free_hours.value == "yes"
    assert verified.rules.no_shared_landlord.value == "yes"


def test_verify_evidence_with_wrapper_words():
    """Kiểm tra LLM trích dẫn thêm chữ thừa (ví dụ 'khu vực trang bị máy giặt') vẫn khớp chính xác."""
    source_text = "Dãy trọ có bãi đậu xe, khu vực trang bị máy giặt và máy sấy."

    extraction = ListingExtraction(
        amenities=Amenities(
            washing_machine=Signal(value="yes", evidence="trang bị máy giặt"),
            parking=Signal(value="yes", evidence="có bãi đậu xe"),
        ),
    )

    verified = extraction.verify_evidence(source_text)
    assert verified.amenities.washing_machine.value == "yes"
    assert verified.amenities.parking.value == "yes"

