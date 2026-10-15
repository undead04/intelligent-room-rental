import pytest
from datetime import datetime
from crawler.schema.enum import RoomType
from crawler.schema.listing import (
    ListingExtraction,
    Signal,
    Amenities,
    Rules,
    Safety,
    ExtractedRoomData,
)
from crawler.etl.transform import (
    clean_room_description,
    build_enriched_embedding_text,
    extract_room_data_from_record,
    ListingTransformer,
)


def test_clean_room_description_comprehensive():
    raw_text = """
    🌟🌟 PHÒNG TRỌ CAO CẤP GẦN ĐH BÁCH KHOA 🌟🌟
    ===============================
    - Giá thuê: 3.500.000 đ/tháng
    - Có máy lạnh, gác lửng, ban công thoáng mát.
    - Giờ giấc tự do, không chung chủ.
    - Xem chi tiết tại: https://phongtro123.com/bai-dang-123
    - Liên hệ SĐT/Zalo: 0909.123.456 hoặc +84 918 234 567 gặp anh Nam
    - Nhanh tay kẻo hết phòng nhé mọi người! #chothuetro #quan10 #giare
    """
    cleaned = clean_room_description(raw_text)

    # 1. URLs, Phone numbers, Hashtags, Emojis must be removed
    assert "https://" not in cleaned
    assert "0909.123.456" not in cleaned
    assert "918 234 567" not in cleaned
    assert "#chothuetro" not in cleaned
    assert "#quan10" not in cleaned
    assert "🌟" not in cleaned
    assert "===" not in cleaned

    # 2. Meaningful descriptive content must be preserved
    assert "PHÒNG TRỌ CAO CẤP GẦN ĐH BÁCH KHOA" in cleaned
    assert "Có máy lạnh, gác lửng, ban công thoáng mát." in cleaned
    assert "Giờ giấc tự do, không chung chủ." in cleaned


def test_clean_room_description_unicode_nfc():
    # Tên phòng với ký tự tổ hợp (NFD: 'e' + combining accent)
    nfd_text = "Pho\u0300ng tro\u0323 Thu\u0309 Đu\u031b\u0301c"
    cleaned = clean_room_description(nfd_text)
    # Sau khi clean phải là NFC
    assert cleaned == "Phòng trọ Thủ Đức"


def test_build_enriched_embedding_text():
    room_data = ExtractedRoomData(
        street="150 Bến Vân Đồn",
        ward="Phường 6",
        district="Quận 4",
        city="Tp Hồ Chí Minh",
        landmarks_nearby=["Cầu Ông Lãnh", "Chợ Bến Thành"],
        room_type=RoomType.STUDIO,
        area=30.0,
        price=1500000,
        standard_amenities=["WC riêng", "máy lạnh", "chỗ để xe", "khóa vân tay/thẻ từ"],
        extra_amenities=["view Landmark 81"],
        rules_and_lifestyle=["giờ giấc tự do", "không chung chủ"],
        is_pet_allowed=True,
    )

    clean_desc = "Phòng mới xây ban công thoáng mát đón nắng sớm."
    enriched_text = build_enriched_embedding_text(room_data, clean_desc=clean_desc)

    # Khối 1: Vị trí
    assert "Vị trí: 150 Bến Vân Đồn, Phường 6, Quận 4, Tp Hồ Chí Minh (Gần: Cầu Ông Lãnh, Chợ Bến Thành)" in enriched_text
    # Khối 2: Đặc điểm & Giá
    assert "Loại phòng: Căn hộ mini / Studio" in enriched_text
    assert "Diện tích: 30.0m2" in enriched_text
    assert "Giá thuê: 1,500,000 VND/tháng" in enriched_text
    # Khối 3: Tiện ích nội khu
    assert "Tiện ích: WC riêng, máy lạnh, chỗ để xe, khóa vân tay/thẻ từ, view Landmark 81" in enriched_text
    # Khối 4: Quy định & Môi trường
    assert "Quy định & Môi trường: giờ giấc tự do, không chung chủ, cho nuôi thú cưng" in enriched_text
    # Khối 5: Mô tả chi tiết
    assert "Mô tả chi tiết:\nPhòng mới xây ban công thoáng mát đón nắng sớm." in enriched_text


def test_extract_room_data_from_record():
    record = {
        "listing_id": "test_rec_1",
        "title": "Phòng đẹp giá rẻ",
        "street_name": "Đường Lê Văn Việt",
        "ward": "Tăng Nhơn Phú A",
        "district": "Quận 9",
        "city": "Tp Hồ Chí Minh",
        "price_vnd": 2500000,
        "area_m2": 20.0,
    }

    report = ListingExtraction(
        room_type=RoomType.ROOM,
        landmarks_nearby=["ĐH Sư Phạm Kỹ Thuật"],
        extra_amenities=["cửa sổ giếng trời"],
        amenities=Amenities(
            aircon=Signal(value="yes", evidence="máy lạnh mới"),
            private_wc=Signal(value="yes", evidence="wc riêng từng phòng"),
            parking=Signal(value="yes", evidence="nhà xe tầng trệt"),
        ),
        rules=Rules(
            pet_allowed=Signal(value="yes", evidence="cho nuôi mèo"),
            free_hours=Signal(value="yes", evidence="giờ giấc tự do"),
        ),
        safety=Safety(
            fingerprint_lock=Signal(value="yes", evidence="cổng khóa vân tay"),
        ),
    )

    extracted = extract_room_data_from_record(record, report)
    assert extracted.street == "Đường Lê Văn Việt"
    assert extracted.district == "Quận 9"
    assert extracted.room_type == RoomType.ROOM
    assert "máy lạnh" in extracted.standard_amenities
    assert "WC riêng" in extracted.standard_amenities
    assert "chỗ để xe" in extracted.standard_amenities
    assert "khóa vân tay/thẻ từ" in extracted.standard_amenities
    assert "cửa sổ giếng trời" in extracted.extra_amenities
    assert extracted.is_pet_allowed is True
    assert "giờ giấc tự do" in extracted.rules_and_lifestyle


def test_listing_transformer_clean_record_and_transform():
    transformer = ListingTransformer()

    raw_items = [
        {
            "listing_id": "nhatot_999",
            "title": "Phòng trọ ban công full nội thất 🌟🌟",
            "description": "Phòng đẹp. Liên hệ SĐT 0909123456 để xem phòng. #phongtro",
            "price_vnd": "3500000",
            "area_m2": "25",
            "lat": "10.77",
            "lng": "106.69",
            "images": ["https://img1.jpg", "https://img2.jpg"],
            "report": {
                "amenities": {
                    "private_wc": {"value": "yes"},
                    "aircon": {"value": "yes"},
                },
                "rules": {
                    "pet_allowed": {"value": "yes"},
                    "free_hours": {"value": "yes"},
                },
                "safety": {
                    "fingerprint_lock": {"value": "yes"},
                },
            },
        },
        # Bản ghi trùng lặp ID (sẽ bị deduplicate)
        {
            "listing_id": "nhatot_999",
            "title": "Bản ghi trùng lặp",
            "price_vnd": 3500000,
            "area_m2": 25,
        },
        # Bản ghi rác thiếu cả giá lẫn diện tích (sẽ bị loại bỏ)
        {
            "listing_id": "nhatot_invalid",
            "title": "Tin rác không có giá và diện tích",
            "price_vnd": 0,
            "area_m2": 0,
        },
    ]

    cleans = transformer.transform(raw_items)

    assert len(cleans) == 1
    item = cleans[0]

    # Kiểm tra cấu trúc khớp với Listing model
    assert item["id"] == "nhatot_999"
    assert item["listing_id"] == "nhatot_999"
    assert item["price_vnd"] == 3500000.0
    assert item["area_m2"] == 25.0
    assert item["price_million_per_m2"] == 0.14  # (3.5 / 25) = 0.14
    assert item["main_image"] == "https://img1.jpg"
    assert item["price_score"] is None  # Reserved for ML price valuation

    # Kiểm tra điểm số
    assert item["safety_score"] is not None
    assert item["amenity_overall"] is not None
    assert isinstance(item["concept_scores"], dict)

    # Kiểm tra chuỗi embedding_text
    assert "embedding_text" in item
    assert "Loại phòng: Phòng trọ" in item["embedding_text"]
    assert "WC riêng" in item["embedding_text"]
    assert "máy lạnh" in item["embedding_text"]
    assert "cho nuôi thú cưng" in item["embedding_text"]
    assert "0909123456" not in item["embedding_text"]
