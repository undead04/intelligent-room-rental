from typing import Any, Dict, List, Optional, Union
from crawler.schema.enum import RoomType
from crawler.schema.listing import ExtractedRoomData, ListingExtraction

# Bản đồ chuyển đổi mã tiện ích sang tiếng Việt chuẩn hóa cho mô hình Embedding
AMENITY_VIETNAMESE_MAP = {
    "private_wc": "WC riêng",
    "aircon": "máy lạnh",
    "mezzanine": "gác lửng",
    "kitchen": "kệ bếp",
    "fridge": "tủ lạnh",
    "washing_machine": "máy giặt",
    "window_balcony": "cửa sổ/ban công",
    "furniture": "nội thất",
    "parking": "chỗ để xe",
    "elevator": "thang máy",
}

SAFETY_VIETNAMESE_MAP = {
    "fingerprint_lock": "khóa vân tay/thẻ từ",
    "camera": "camera an ninh",
    "guard": "bảo vệ 24/7",
    "safe_area": "khu an ninh",
}

ROOM_TYPE_LABELS = {
    "ROOM": "Phòng trọ",
    "STUDIO": "Căn hộ mini / Studio",
    "APARTMENT": "Căn hộ chung cư",
    "SLEEPBOX": "Ký túc xá / Sleepbox",
    "WHOLE_HOUSE": "Nhà nguyên căn",
}


def build_enriched_embedding_text(
    data: Union[ExtractedRoomData, Any],
    clean_desc: str = "",
    prefix: str = "",
) -> str:
    """Tạo chuỗi văn bản giàu ngữ cảnh 5 khối để đưa vào mô hình Embedding.
    Hỗ trợ tùy chọn prefix (ví dụ: 'passage: ' cho multilingual-e5-base).

    Cấu trúc 5 khối:
    1. Vị trí & Tiện ích ngoại khu (đường, phường, quận, thành phố + địa danh gần đó)
    2. Đặc điểm & Giá (loại phòng, diện tích, giá thuê VND/tháng)
    3. Tiện ích nội khu (chuẩn hóa tiếng Việt + tiện ích phụ)
    4. Môi trường & Quy định (lối sống, nuôi thú cưng)
    5. Mô tả thực tế đã dọn dẹp sạch sẽ
    """
    blocks = []

    def _dedup(items: list[Any]) -> list[str]:
        seen = set()
        res = []
        for x in items:
            s = str(getattr(x, "value", x) if x is not None else "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                res.append(s)
        return res

    # 1. Địa điểm & Tiện ích ngoại khu
    loc_tokens = [
        t for t in [
            getattr(data, "street", None),
            getattr(data, "ward", None),
            getattr(data, "district", None),
            getattr(data, "city", None),
        ] if t
    ]
    loc_str = ", ".join(loc_tokens) if loc_tokens else "Không xác định"
    landmarks = _dedup(getattr(data, "landmarks_nearby", []) or [])
    if landmarks:
        near_str = ", ".join(landmarks)
        loc_str += f" (Gần: {near_str})"
    blocks.append(f"Vị trí: {loc_str}")

    # 2. Đặc điểm & Giá
    specs = []
    raw_rt = getattr(data, "room_type", RoomType.ROOM)
    rt_val = raw_rt.value if hasattr(raw_rt, "value") else str(raw_rt)
    rt_label = ROOM_TYPE_LABELS.get(rt_val, rt_val)
    specs.append(f"Loại phòng: {rt_label}")

    area = getattr(data, "area", None)
    if area:
        specs.append(f"Diện tích: {area}m2")

    price = getattr(data, "price", None)
    if price and price > 0:
        specs.append(f"Giá thuê: {int(price):,} VND/tháng")
    blocks.append(" | ".join(specs))

    # 3. Tiện ích nội khu (gộp cả chuẩn hóa lẫn mô tả phụ)
    std_amenities = getattr(data, "standard_amenities", []) or []
    extra_amenities = getattr(data, "extra_amenities", []) or []
    amenity_labels = _dedup(std_amenities + list(extra_amenities))
    if amenity_labels:
        amen_str = ", ".join(amenity_labels)
        blocks.append(f"Tiện ích: {amen_str}")

    # 4. Môi trường & Quy định
    rule_items = list(getattr(data, "rules_and_lifestyle", []) or [])
    is_pet_allowed = getattr(data, "is_pet_allowed", None)
    if is_pet_allowed is True:
        rule_items.append("cho nuôi thú cưng")
    elif is_pet_allowed is False:
        rule_items.append("không cho nuôi thú cưng")
    rule_items = _dedup(rule_items)
    if rule_items:
        rule_str = ", ".join(rule_items)
        blocks.append(f"Quy định & Môi trường: {rule_str}")

    # 5. Mô tả thực tế đã dọn dẹp
    if clean_desc:
        blocks.append(f"Mô tả chi tiết:\n{clean_desc}")

    body = "\n".join(blocks)
    if prefix:
        return f"{prefix.strip()} {body}"
    return body


def extract_room_data_from_record(
    record: dict,
    report: Optional[Union[ListingExtraction, dict]] = None,
) -> ExtractedRoomData:
    """Chuyển đổi bản ghi cào thô và báo cáo LLM sang ExtractedRoomData."""
    street = record.get("street_name") or record.get("street") or record.get("address_raw")
    ward = record.get("ward")
    district = record.get("district")
    city = record.get("city")
    area = record.get("area_m2")
    price = record.get("price_vnd")
    room_type = record.get("room_type") or RoomType.ROOM

    landmarks_nearby: List[str] = []
    extra_amenities: List[str] = []
    rules_and_lifestyle: List[str] = []
    standard_amenities: List[str] = []
    is_pet_allowed: Optional[bool] = None

    if report:
        rep_obj = None
        if isinstance(report, dict):
            try:
                rep_obj = ListingExtraction.model_validate(report)
            except Exception:
                rep_obj = None
        elif isinstance(report, ListingExtraction):
            rep_obj = report

        if rep_obj:
            room_type = rep_obj.room_type
            landmarks_nearby = list(rep_obj.landmarks_nearby or [])
            extra_amenities = list(rep_obj.extra_amenities or [])
            rules_and_lifestyle = list(rep_obj.rules_and_lifestyle or [])

            # Tiện ích phòng
            for k, label in AMENITY_VIETNAMESE_MAP.items():
                sig = getattr(rep_obj.amenities, k, None)
                if sig and getattr(sig, "value", None) == "yes" and label not in standard_amenities:
                    standard_amenities.append(label)

            # An ninh & an toàn
            for k, label in SAFETY_VIETNAMESE_MAP.items():
                sig = getattr(rep_obj.safety, k, None)
                if sig and getattr(sig, "value", None) == "yes" and label not in standard_amenities:
                    standard_amenities.append(label)

            # Quy định & Thú cưng
            if rep_obj.rules.pet_allowed.value == "yes":
                is_pet_allowed = True
            elif rep_obj.rules.pet_allowed.value == "no":
                is_pet_allowed = False

            if rep_obj.rules.free_hours.value == "yes" and "giờ giấc tự do" not in rules_and_lifestyle:
                rules_and_lifestyle.append("giờ giấc tự do")
            if rep_obj.rules.no_shared_landlord.value == "yes" and "không chung chủ" not in rules_and_lifestyle:
                rules_and_lifestyle.append("không chung chủ")
        elif isinstance(report, dict):
            # Fallback khi report là dict thô
            if "landmarks_nearby" in report:
                landmarks_nearby = list(report["landmarks_nearby"] or [])
            if "extra_amenities" in report:
                extra_amenities = list(report["extra_amenities"] or [])
            if "rules_and_lifestyle" in report:
                rules_and_lifestyle = list(report["rules_and_lifestyle"] or [])
            if "room_type" in report:
                room_type = report["room_type"]

            amenities_dict = report.get("amenities") or {}
            for k, label in AMENITY_VIETNAMESE_MAP.items():
                val = amenities_dict.get(k, {})
                v_str = val.get("value") if isinstance(val, dict) else val
                if v_str == "yes" and label not in standard_amenities:
                    standard_amenities.append(label)

            safety_dict = report.get("safety") or {}
            for k, label in SAFETY_VIETNAMESE_MAP.items():
                val = safety_dict.get(k, {})
                v_str = val.get("value") if isinstance(val, dict) else val
                if v_str == "yes" and label not in standard_amenities:
                    standard_amenities.append(label)

            rules_dict = report.get("rules") or {}
            pet_sig = rules_dict.get("pet_allowed", {})
            pet_val = pet_sig.get("value") if isinstance(pet_sig, dict) else pet_sig
            if pet_val == "yes":
                is_pet_allowed = True
            elif pet_val == "no":
                is_pet_allowed = False

    return ExtractedRoomData(
        street=street,
        ward=ward,
        district=district,
        city=city,
        landmarks_nearby=landmarks_nearby,
        room_type=room_type,
        area=float(area) if area else None,
        price=float(price) if price else None,
        standard_amenities=standard_amenities,
        extra_amenities=extra_amenities,
        rules_and_lifestyle=rules_and_lifestyle,
        is_pet_allowed=is_pet_allowed,
    )
