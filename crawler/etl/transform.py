import os
import sys
import re
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import pandas as pd

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.schema.enum import RoomType, AmenityCode
from crawler.schema.listing import (
    ListingExtraction,
    ExtractedRoomData,
    SingleListingExtraction,
    ChunkExtractionWrapper,
)

# Bản đồ chuyển đổi tiện ích sang nhãn tiếng Việt cho chuỗi Embedding
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


def clean_room_description(text: str) -> str:
    """Làm sạch tiêu đề và mô tả bài đăng:
    - Chuẩn hóa Unicode NFC
    - Loại bỏ URL, link web
    - Loại bỏ số điện thoại liên hệ
    - Loại bỏ hashtag
    - Loại bỏ ký tự trang trí, viền khung, bullet point rác
    - Loại bỏ Emojis & Icon
    - Loại bỏ các dòng liên hệ / chốt sale vô nghĩa
    - Chuẩn hóa khoảng trắng & dòng trống
    """
    if not text:
        return ""

    # 1. Chuẩn hóa Unicode (tránh lỗi ký tự dựng sẵn vs tổ hợp trong tiếng Việt)
    text = unicodedata.normalize("NFC", str(text))

    # 2. Xóa URL / Link web
    text = re.sub(r"https?://\S+|www\.\S+", "", text)

    # 3. Xóa số điện thoại (các dạng: 0909123456, 0909.123.456, 0909 123 456, +84...)
    text = re.sub(r"(?:\+?84|0)(?:\s*[\.\-]?\s*\d){9,10}\b", "", text)

    # 4. Xóa Hashtag (e.g., #chothuetro, #thuduc)
    text = re.sub(r"#\w+", "", text)

    # 5. Xóa ký tự trang trí, đường kẻ khung (====, ----, *****, bullet points rác)
    text = re.sub(r"[═=\-_*~•❖▶★●◆✔☎►]{2,}", " ", text)

    # 6. Xóa Emoji / Icon & Variation Selectors
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map Symbols
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"
        "\uFE0E\uFE0F"          # Variation selectors
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub(" ", text)

    # 7. Xóa toàn bộ các dòng thuần liên hệ, chốt sale
    contact_line_pattern = re.compile(
        r"^\s*[-•*+]?\s*(?:liên hệ|inbox|ib|zalo|call|alo|gọi ngay|sđt|hotline|nhanh tay|xem phòng|xem chi tiết).*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = contact_line_pattern.sub("", text)

    # Xóa các cụm từ chốt sale còn sót lại
    cta_patterns = [
        r"(?:liên hệ|inbox|ib|zalo|call|alo|gọi ngay|sđt|hotline)[\s\:\-\/]*",
        r"nhanh tay kẻo hết.*",
        r"xem phòng trực tiếp.*",
    ]
    for pattern in cta_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # 8. Lọc bỏ các dòng rác chỉ còn lại dấu gạch đầu dòng hoặc dấu câu mồ côi
    lines = []
    for line in text.split("\n"):
        line_clean = re.sub(r"^\s*[-•*+:\./\s]+$", "", line).strip()
        if line_clean:
            lines.append(line_clean)
    text = "\n".join(lines)

    # 9. Chuẩn hóa khoảng trắng và xuống dòng thừa
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def build_enriched_embedding_text(data: Union[ExtractedRoomData, Any], clean_desc: str = "") -> str:
    """Tạo chuỗi văn bản giàu ngữ cảnh 5 khối để đưa vào mô hình Embedding:
    1. Vị trí & Tiện ích ngoại khu (đường, phường, quận, thành phố + địa danh gần đó)
    2. Đặc điểm & Giá (loại phòng, diện tích, giá thuê VND/tháng)
    3. Tiện ích nội khu (chuẩn hóa tiếng Việt + tiện ích phụ)
    4. Môi trường & Quy định (lối sống, nuôi thú cưng)
    5. Mô tả thực tế đã dọn dẹp sạch sẽ
    """
    blocks = []

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
    landmarks = getattr(data, "landmarks_nearby", []) or []
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
    amenity_labels = [getattr(a, "value", str(a)) for a in std_amenities] + list(extra_amenities)
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
    if rule_items:
        rule_str = ", ".join(rule_items)
        blocks.append(f"Quy định & Môi trường: {rule_str}")

    # 5. Mô tả thực tế đã dọn dẹp
    if clean_desc:
        blocks.append(f"Mô tả chi tiết:\n{clean_desc}")

    return "\n".join(blocks)


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
            # Fallback khi report là dict thô không khớp ListingExtraction đầy đủ
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


class ListingTransformer:
    """
    [TRANSFORM STAGE]
    Chịu trách nhiệm:
    1. Làm sạch, chuẩn hóa kiểu dữ liệu số và thời gian.
    2. Khử trùng lặp bản ghi.
    3. Tích hợp báo cáo LLM: tính điểm safety_score, amenity_overall_score, concept_scores.
    4. Giữ price_score = None (để chờ mô hình ML định giá).
    5. Sinh chuỗi văn bản giàu ngữ cảnh embedding_text cho mô hình Embedding.
    6. Xuất cấu trúc tương thích 100% với model Listing và ListingEmbedding.
    """

    def __init__(self, llm_reports: Optional[Union[dict, list, str, Path]] = None):
        self.llm_reports = self._load_reports(llm_reports)

    def _load_reports(self, reports_source: Any) -> dict[str, Any]:
        """Tải báo cáo LLM từ dict, list hoặc đường dẫn file checkpoint.json / datas.json."""
        if not reports_source:
            return {}
        if isinstance(reports_source, dict):
            if "results" in reports_source:
                return {
                    str(r.get("listing_id") or r.get("id")): r.get("report")
                    for r in reports_source["results"]
                }
            return {str(k): v for k, v in reports_source.items()}
        if isinstance(reports_source, list):
            res = {}
            for r in reports_source:
                lid = str(r.get("listing_id") or r.get("id") or "")
                if lid:
                    res[lid] = r.get("report") or r
            return res
        if isinstance(reports_source, (str, Path)):
            path = Path(reports_source)
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return self._load_reports(data)
                except Exception as e:
                    print(f"[TRANSFORM] Không thể đọc báo cáo từ {path}: {e}")
        return {}

    def clean_number(self, value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        """Ép kiểu số thực an toàn."""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def clean_int(self, value: Any, default: Optional[int] = None) -> Optional[int]:
        """Ép kiểu số nguyên an toàn."""
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

    def to_datetime(self, date_string: Any) -> Optional[datetime]:
        """Chuẩn hóa trường ngày giờ."""
        if not date_string:
            return None
        if isinstance(date_string, datetime):
            return date_string
        try:
            return pd.to_datetime(date_string, format="mixed", errors="coerce").to_pydatetime()
        except Exception:
            return None

    def clean_record(self, item: dict, report: Optional[Union[ListingExtraction, dict]] = None) -> dict:
        """Chuẩn hóa từng bản ghi khớp schema của model Listing và ListingEmbedding."""
        record = dict(item)

        # 1. ID định danh thống nhất
        lid = str(record.get("listing_id") or record.get("id") or "")
        record["id"] = lid
        record["listing_id"] = lid
        record["source"] = str(record.get("source") or "nhatot")
        record["url"] = record.get("url")

        # 2. Làm sạch tiêu đề & mô tả
        raw_title = str(record.get("title") or "")
        raw_desc = str(record.get("description") or "")
        clean_title = clean_room_description(raw_title)
        clean_desc = clean_room_description(raw_desc)

        record["clean_title"] = clean_title
        record["clean_description"] = clean_desc
        record["title"] = clean_title or raw_title or "Untitled"
        record["description"] = clean_desc or raw_desc

        # 3. Chuẩn hóa số học tài chính
        price_vnd = self.clean_number(record.get("price_vnd"))
        area_m2 = self.clean_number(record.get("area_m2"))
        record["price_vnd"] = price_vnd
        record["area_m2"] = area_m2

        price_million_per_m2 = self.clean_number(record.get("price_million_per_m2"), default=None)
        if (price_million_per_m2 is None or price_million_per_m2 <= 0) and price_vnd > 0 and area_m2 > 0:
            price_million_per_m2 = round((price_vnd / 1_000_000.0) / area_m2, 2)
        record["price_million_per_m2"] = price_million_per_m2

        record["deposit"] = self.clean_number(record.get("deposit"), default=None)
        record["furnishing_code"] = self.clean_int(record.get("furnishing_code"), default=None)
        record["price_string"] = record.get("price_string") or (f"{int(price_vnd):,} đ/tháng" if price_vnd > 0 else None)

        # 4. Tọa độ & Địa chỉ
        record["lat"] = self.clean_number(record.get("lat"), default=None)
        record["lng"] = self.clean_number(record.get("lng"), default=None)
        record["address_raw"] = record.get("address_raw") or record.get("street_name") or record.get("street")

        # 5. Hình ảnh
        raw_images = record.get("images")
        if isinstance(raw_images, str) and raw_images.startswith("["):
            try:
                parsed_imgs = json.loads(raw_images)
                if isinstance(parsed_imgs, list):
                    raw_images = parsed_imgs
            except Exception:
                pass
        elif isinstance(raw_images, str) and "|" in raw_images:
            raw_images = [img.strip() for img in raw_images.split("|") if img.strip()]

        if isinstance(raw_images, list):
            record["images"] = raw_images
            if not record.get("main_image") and raw_images:
                record["main_image"] = raw_images[0]
        else:
            record["images"] = []

        if not record.get("main_image"):
            record["main_image"] = record.get("image") or None

        # 6. Khóa ngoại liên kết địa lý & người đăng
        record["ward_id"] = self.clean_int(record.get("ward_id"))
        record["district_id"] = self.clean_int(record.get("district_id"))
        record["region_id"] = self.clean_int(record.get("region_id"))
        record["room_type_id"] = self.clean_int(record.get("room_type_id"))
        record["category_id"] = self.clean_int(record.get("category_id"))
        record["poster_id"] = str(record.get("poster_id") or "") or None

        # 7. Trạng thái và thời gian
        record["is_active"] = bool(record.get("is_active", True))
        record["status"] = str(record.get("status") or "active").lower()
        record["posted_date"] = self.to_datetime(record.get("posted_date") or record.get("posted_at"))
        record["crawled_at"] = self.to_datetime(record.get("crawled_at")) or datetime.now()

        # 8. Tích hợp báo cáo trích xuất LLM (Safety, Amenities, Concept Scores)
        rep = report or self.llm_reports.get(lid) or record.get("report")
        if rep:
            rep_obj = None
            if isinstance(rep, dict):
                try:
                    rep_obj = ListingExtraction.model_validate(rep)
                except Exception:
                    rep_obj = None
            elif isinstance(rep, ListingExtraction):
                rep_obj = rep

            if rep_obj:
                record["safety_score"] = rep_obj.safety_score()
                record["amenity_overall"] = rep_obj.amenity_overall_score()
                record["concept_scores"] = rep_obj.to_concept_scores()
                record["report"] = rep_obj.model_dump(mode="json")
                if hasattr(rep_obj.room_type, "value"):
                    record["room_type"] = rep_obj.room_type.value
            elif isinstance(rep, dict):
                record["safety_score"] = self.clean_number(rep.get("safety_score"), default=None)
                record["amenity_overall"] = self.clean_number(rep.get("amenity_overall_score") or rep.get("amenity_overall"), default=None)
                record["concept_scores"] = rep.get("concept_scores")
                record["report"] = rep
        else:
            record["safety_score"] = self.clean_number(record.get("safety_score"), default=None)
            record["amenity_overall"] = self.clean_number(record.get("amenity_overall"), default=None)
            record["concept_scores"] = record.get("concept_scores")

        # 9. Giữ price_score = None (chờ tích hợp ML định giá nhà)
        record["price_score"] = None

        # 10. Tạo chuỗi văn bản giàu ngữ cảnh cho mô hình Embedding
        extracted_data = extract_room_data_from_record(record, rep)
        desc_for_embed = f"{clean_title}\n{clean_desc}".strip() if clean_title and clean_title not in clean_desc else clean_desc
        record["embedding_text"] = build_enriched_embedding_text(extracted_data, clean_desc=desc_for_embed)

        return record

    def deduplicate(self, records: list[dict]) -> list[dict]:
        """Khử trùng lặp dựa trên listing_id hoặc id gốc."""
        seen_ids = set()
        unique_records = []

        for r in records:
            lid = str(r.get("listing_id") or r.get("id") or "")
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                unique_records.append(r)
            elif not lid:
                unique_records.append(r)

        return unique_records

    def transform(
        self,
        raw_records: list[dict],
        llm_reports: Optional[Union[dict, list, str, Path]] = None,
        active_only: bool = False,
    ) -> list[dict]:
        """Chạy toàn bộ quy trình Transform:
        1. Nạp báo cáo trích xuất LLM (nếu có).
        2. Khử trùng lặp dữ liệu thô.
        3. Chuẩn hóa từng bản ghi và sinh văn bản embedding_text.
        4. Lọc bỏ các tin rác không hợp lệ (giá <= 0 và diện tích <= 0).
        5. Tùy chọn chỉ lấy tin đang active.
        """
        print(f"[TRANSFORM] Bắt đầu xử lý {len(raw_records)} bản ghi thô...", flush=True)

        reports_map = self._load_reports(llm_reports) if llm_reports else self.llm_reports

        # 1. Khử trùng lặp
        deduped = self.deduplicate(raw_records)
        print(f"[TRANSFORM] Sau khi khử trùng lặp: còn {len(deduped)} bản ghi.", flush=True)

        cleaned_records = []
        skipped_invalid = 0

        for r in deduped:
            lid = str(r.get("listing_id") or r.get("id") or "")
            report_for_item = reports_map.get(lid) if reports_map else None

            cleaned = self.clean_record(r, report=report_for_item)

            # Loại bỏ các tin rác không có cả giá lẫn diện tích
            if cleaned["price_vnd"] <= 0 and cleaned["area_m2"] <= 0:
                skipped_invalid += 1
                continue

            # Lọc nếu chỉ muốn lấy tin active
            if active_only and not cleaned["is_active"]:
                continue

            cleaned_records.append(cleaned)

        if skipped_invalid > 0:
            print(f"[TRANSFORM] Đã loại bỏ {skipped_invalid} bản ghi không hợp lệ (thiếu giá & diện tích).", flush=True)

        print(f"[TRANSFORM] Hoàn tất Transform! Thu được {len(cleaned_records)} bản ghi sạch sẵn sàng nạp CSDL & Embedding.", flush=True)
        return cleaned_records


if __name__ == "__main__":
    from crawler.etl.extract import extract_raw_listings

    raws = extract_raw_listings()
    transformer = ListingTransformer()
    cleans = transformer.transform(raws)
    if cleans:
        print(f"Bản ghi mẫu đầu tiên: {cleans[0]['title']} - Giá: {cleans[0]['price_vnd']} VNĐ")
        print("\n--- Embedding Text Mẫu ---")
        print(cleans[0].get("embedding_text"))
