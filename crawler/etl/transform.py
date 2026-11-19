import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
import pandas as pd

# Đảm bảo root dự án có trong sys.path khi chạy file độc lập
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from crawler.schema.enums import RoomType, ROOM_TYPE_CODE_TO_ID
from crawler.schema.listing import ListingExtraction
from crawler.etl.text_cleaner import clean_room_description
from crawler.etl.enricher import (
    build_enriched_embedding_text,
    extract_room_data_from_record,
)

_P_NON_RESIDENTIAL_AD = re.compile(
    r"(?:cho\s*thuê|sang\s*nhượng)\s*(?:kho\b|kho\s*xưởng|kho\s*chứa|xưởng|mặt\s*bằng\s*kinh\s*doanh|ki\s*ốt|kiot|sạp\s*chợ)"
    r"|cho\s*thục\b|cho\s*thụt\b",
    re.IGNORECASE,
)
_P_DAILY_RENTAL = re.compile(
    r"thuê\s*theo\s*(?:ngày|giờ)|\b\d{2,3}\s*k\s*/\s*(?:ngày|đêm|giờ)\b",
    re.IGNORECASE,
)
_P_KTX_TITLE = re.compile(
    r"\bktx\b|ký\s*túc\s*xá|ki\s*tuc\s*xa|sleep\s*box|sleepbox|hộp\s*ngủ|giường\s*tầng",
    re.IGNORECASE,
)
_P_OGHEP_TITLE = re.compile(
    r"ở\s*ghép|o\s*ghep|tìm\s*(?:\d+\s*)?(?:bạn|nam|nữ|người)\s*ở\s*(?:ghép|chung)|share\s*phòng|ghép\s*phòng",
    re.IGNORECASE,
)
_P_STUDIO_TITLE = re.compile(
    r"\bstudio\b|\bchdv\b|căn\s*hộ\s*dịch\s*vụ|can\s*ho\s*dich\s*vu|\bduplex\b",
    re.IGNORECASE,
)

_VIETNAM_LAT_RANGE = (8.0, 23.5)
_VIETNAM_LNG_RANGE = (102.0, 110.0)
_ROOM_TYPE_FILTER_RULES: dict[int, dict[str, tuple[float, float]]] = {
    1: {"area": (6.0, 100.0), "price": (500_000.0, 15_000_000.0), "ppm": (12_000.0, 500_000.0)},
    2: {"area": (12.0, 90.0), "price": (1_200_000.0, 20_000_000.0), "ppm": (40_000.0, 700_000.0)},
    3: {"area": (15.0, 160.0), "price": (1_000_000.0, 30_000_000.0), "ppm": (15_000.0, 700_000.0)},
    4: {"area": (3.0, 120.0), "price": (400_000.0, 4_500_000.0), "ppm": (5_000.0, 800_000.0)},
    5: {"area": (12.0, 250.0), "price": (1_500_000.0, 35_000_000.0), "ppm": (12_000.0, 600_000.0)},
}


def _is_valid_transformed_record(cleaned: dict[str, object]) -> bool:
    """Kiểm tra giá, diện tích, tọa độ Việt Nam và ngưỡng hợp lệ theo từng loại phòng."""
    price_val = cleaned.get("price_vnd")
    area_val = cleaned.get("area_m2")
    try:
        price = float(price_val) if price_val is not None else 0.0  # type: ignore[arg-type]
        area = float(area_val) if area_val is not None else 0.0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False

    if price <= 0.0 or area <= 0.0:
        return False

    lat_val = cleaned.get("lat")
    lng_val = cleaned.get("lng")
    if lat_val is not None or lng_val is not None:
        if lat_val is None or lng_val is None:
            return False
        try:
            lat = float(lat_val)  # type: ignore[arg-type]
            lng = float(lng_val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if not (
            _VIETNAM_LAT_RANGE[0] <= lat <= _VIETNAM_LAT_RANGE[1]
            and _VIETNAM_LNG_RANGE[0] <= lng <= _VIETNAM_LNG_RANGE[1]
        ):
            return False

    rt_raw = cleaned.get("room_type_id")
    try:
        rt_id = int(rt_raw) if rt_raw is not None else 1  # type: ignore[arg-type]
    except (TypeError, ValueError):
        rt_id = 1
    rule = _ROOM_TYPE_FILTER_RULES.get(rt_id, _ROOM_TYPE_FILTER_RULES[1])
    ppm = price / area
    return (
        rule["area"][0] <= area <= rule["area"][1]
        and rule["price"][0] <= price <= rule["price"][1]
        and rule["ppm"][0] <= ppm <= rule["ppm"][1]
    )


class ListingTransformer:
    """
    [TRANSFORM STAGE]
    Chịu trách nhiệm:
    1. Làm sạch, chuẩn hóa kiểu dữ liệu số và thời gian.
    2. Khử trùng lặp bản ghi.
    3. Tích hợp báo cáo LLM: tính điểm safety_score, amenity_overall_score, concept_scores, room_type.
    4. Giữ price_score = None (để chờ mô hình ML định giá).
    5. Sinh chuỗi văn bản giàu ngữ cảnh embedding_text cho mô hình Embedding.
    6. Xuất cấu trúc tương thích 100% với model Listing và ListingEmbedding.
    """

    def __init__(
        self,
        llm_reports: Optional[Union[dict[str, object], list[dict[str, object]], str, Path]] = None,
        enable_price_evaluator: bool = False,
    ) -> None:
        self.llm_reports = self._load_reports(llm_reports)
        self.enable_price_evaluator = enable_price_evaluator

    def _load_reports(
        self,
        reports_source: Optional[Union[dict[str, object], list[dict[str, object]], str, Path]] = None,
    ) -> dict[str, object]:
        """Tải báo cáo LLM từ dict, list hoặc đường dẫn file checkpoint (.jsonl / .json)."""
        if not reports_source:
            return {}

        raw_data = reports_source
        if isinstance(reports_source, (str, Path)):
            path_str = str(reports_source)
            if not os.path.exists(path_str):
                return {}

            # Ưu tiên đọc định dạng JSONL (tốc độ cao)
            if path_str.endswith(".jsonl"):
                reports = {}
                try:
                    with open(path_str, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                            except Exception:
                                continue
                            if "__meta__" in item or ("metadata" in item and len(item) == 1):
                                continue
                            lid = str(item.get("listing_id") or item.get("id") or "").strip()
                            rep = item.get("report") or item
                            if lid:
                                reports[lid] = rep
                                if "_" in lid:
                                    reports[lid.split("_", 1)[-1]] = rep
                                else:
                                    reports[f"nhatot_{lid}"] = rep
                    return reports
                except Exception as e:
                    print(f"[TRANSFORM] Lỗi đọc file checkpoint JSONL {path_str}: {e}", flush=True)
                    return {}

            # Đọc JSON truyền thống
            try:
                with open(path_str, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception as e:
                print(f"[TRANSFORM] Lỗi đọc file checkpoint báo cáo LLM {path_str}: {e}", flush=True)
                return {}

        # Xử lý khi raw_data là dict hoặc list
        reports = {}
        items = raw_data.get("results", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])
        if isinstance(raw_data, dict) and "results" not in raw_data:
            items = [{"listing_id": k, "report": v} for k, v in raw_data.items()]

        for item in items:
            lid = str(item.get("listing_id") or item.get("id") or "").strip()
            rep = item.get("report") or item
            if lid:
                reports[lid] = rep
                if "_" in lid:
                    reports[lid.split("_", 1)[-1]] = rep
                else:
                    reports[f"nhatot_{lid}"] = rep
        return reports

    def clean_number(self, value: Optional[Union[str, int, float]], default: Optional[float] = 0.0) -> Optional[float]:
        """Ép kiểu số thực an toàn."""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def clean_int(self, value: Optional[Union[str, int, float]], default: Optional[int] = None) -> Optional[int]:
        """Ép kiểu số nguyên an toàn."""
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

    def clean_positive_int(self, *candidates: object) -> Optional[int]:
        """Chọn giá trị số nguyên dương (> 0) đầu tiên hợp lệ, bỏ qua bool và giá trị <= 0."""
        for val in candidates:
            if val is None or isinstance(val, bool) or val == "":
                continue
            parsed = self.clean_int(val, default=None)
            if parsed is not None and parsed > 0:
                return parsed
        return None

    def to_datetime(self, date_string: Optional[Union[str, int, float, datetime]]) -> Optional[datetime]:
        """Chuẩn hóa trường ngày giờ."""
        if not date_string:
            return None
        if isinstance(date_string, datetime):
            return date_string
        try:
            return pd.to_datetime(date_string, format="mixed", errors="coerce").to_pydatetime()
        except Exception:
            return None

    def clean_record(
        self,
        item: dict[str, object],
        report: Optional[Union[ListingExtraction, dict[str, object]]] = None,
    ) -> dict[str, object]:
        """Chuẩn hóa từng bản ghi khớp schema của model Listing và ListingEmbedding."""
        record: dict[str, object] = dict(item)

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
        record["title"] = raw_title or "Untitled"
        record["description"] = raw_desc

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
        raw_bedrooms = self.clean_positive_int(
            record.get("bedrooms"), record.get("num_bedrooms"), record.get("rooms")
        )
        raw_bathrooms = self.clean_positive_int(
            record.get("bathrooms"), record.get("num_bathrooms"), record.get("toilets")
        )
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
        record["poster_id"] = str(record.get("poster_id") or "") or None

        # 7. Trạng thái và thời gian
        record["is_active"] = bool(record.get("is_active", True))
        record["status"] = str(record.get("status") or "active").lower()
        record["last_checked_at"] = self.to_datetime(record.get("last_checked_at"))
        record["posted_date"] = self.to_datetime(record.get("posted_date") or record.get("posted_at"))
        record["crawled_at"] = self.to_datetime(record.get("crawled_at")) or datetime.now()

        # 8. Tích hợp báo cáo trích xuất LLM (Safety, Amenities, Concept Scores)
        rep = (
            report
            or self.llm_reports.get(lid)
            or (self.llm_reports.get(lid.split("_", 1)[-1]) if "_" in lid else None)
            or self.llm_reports.get(f"nhatot_{lid}")
            or record.get("report")
        )
        rep_obj = None
        llm_bedrooms = None
        llm_bathrooms = None
        if rep:
            if isinstance(rep, dict):
                try:
                    rep_obj = ListingExtraction.model_validate(rep)
                except Exception:
                    rep_obj = None
            elif isinstance(rep, ListingExtraction):
                rep_obj = rep

            if rep_obj:
                record["concept_scores"] = rep_obj.to_concept_scores()
                record["report"] = rep_obj.model_dump(mode="json")
                if getattr(rep_obj, "numeric", None):
                    llm_bedrooms = rep_obj.numeric.bedrooms
                    llm_bathrooms = rep_obj.numeric.bathrooms
            elif isinstance(rep, dict):
                record["safety_score"] = self.clean_number(rep.get("safety_score"), default=None)
                record["amenity_overall"] = self.clean_number(rep.get("amenity_overall_score") or rep.get("amenity_overall"), default=None)
                record["concept_scores"] = rep.get("concept_scores")
                record["report"] = rep
                num_dict = rep.get("numeric") or {}
                if isinstance(num_dict, dict):
                    llm_bedrooms = num_dict.get("bedrooms")
                    llm_bathrooms = num_dict.get("bathrooms")
        else:
            record["safety_score"] = self.clean_number(record.get("safety_score"), default=None)
            record["amenity_overall"] = self.clean_number(record.get("amenity_overall"), default=None)
            record["concept_scores"] = record.get("concept_scores")

        final_bedrooms = self.clean_positive_int(llm_bedrooms, raw_bedrooms)
        final_bathrooms = self.clean_positive_int(llm_bathrooms, raw_bathrooms)
        record["bedrooms"] = final_bedrooms
        record["bathrooms"] = final_bathrooms
        if final_bedrooms is not None:
            record["num_bedrooms"] = final_bedrooms
        else:
            record.pop("num_bedrooms", None)
        if final_bathrooms is not None:
            record["num_bathrooms"] = final_bathrooms
        else:
            record.pop("num_bathrooms", None)

        raw_furnishing_code = record["furnishing_code"]

        # 8.5. Tự động điền furnishing_code = 2 (Nội thất đầy đủ) nếu hiện tại là None và LLM phát hiện có nội thất
        if record["furnishing_code"] is None and self._has_llm_furniture(rep_obj, rep, record):
            record["furnishing_code"] = 2

        # 9. Chuẩn hóa phân loại phòng (room_type & room_type_id) theo canonical 1..5
        room_type_val = None
        if rep_obj and rep_obj.room_type:
            room_type_val = rep_obj.room_type.value if hasattr(rep_obj.room_type, "value") else str(rep_obj.room_type)
        elif isinstance(rep, dict) and rep.get("room_type"):
            room_type_val = rep.get("room_type")
        elif record.get("room_type"):
            room_type_val = record.get("room_type")

        norm_code = str(room_type_val).strip().upper() if room_type_val else RoomType.ROOM.value
        if norm_code not in ROOM_TYPE_CODE_TO_ID:
            norm_code = RoomType.ROOM.value

        # Quy tắc nghiệp vụ:
        # - Giá thuê dưới 1.000.000 VNĐ (< 1 củ), hoặc tiêu đề KTX/Sleepbox (<= 3.5tr), hoặc tìm người ở ghép (<= 3tr) -> SLEEPBOX
        # - Tiêu đề ghi rõ Studio/CHDV/Duplex (>= 3.5tr) đang gán ROOM -> STUDIO
        p_val = price_vnd or 0.0
        if (
            (0 < p_val < 1_000_000)
            or (0 < p_val <= 3_500_000 and _P_KTX_TITLE.search(clean_title))
            or (0 < p_val <= 3_000_000 and _P_OGHEP_TITLE.search(clean_title))
        ):
            norm_code = RoomType.SLEEPBOX.value
        elif norm_code == RoomType.ROOM.value and p_val >= 3_500_000 and _P_STUDIO_TITLE.search(clean_title):
            norm_code = RoomType.STUDIO.value

        record["room_type"] = norm_code
        record["room_type_id"] = ROOM_TYPE_CODE_TO_ID[norm_code]
        if isinstance(record.get("report"), dict):
            record["report"] = {**record["report"], "room_type": norm_code}

        # 9.5. Chấm safety_score & amenity_overall v2 sau khi đã chốt room_type, bathrooms và giữ raw_furnishing_code gốc
        desc_for_embed = f"{clean_title}\n{clean_desc}".strip()
        if rep_obj is not None:
            record["safety_score"] = rep_obj.safety_score(
                room_type=norm_code,
                source_text=desc_for_embed,
            )
            record["amenity_overall"] = rep_obj.amenity_overall_score(
                room_type=norm_code,
                furnishing_code=raw_furnishing_code,
                bathrooms=final_bathrooms,
                source_text=desc_for_embed,
            )

        # 10. Giữ price_score (nếu đã có thì giữ nguyên, ngược lại để None chờ ML định giá)
        record["price_score"] = self.clean_number(record.get("price_score"), default=None)

        # 10. Tạo chuỗi văn bản giàu ngữ cảnh cho mô hình Embedding
        extracted_data = extract_room_data_from_record(record, rep)
        extracted_data.room_type = RoomType(norm_code)
        record["embedding_text"] = build_enriched_embedding_text(extracted_data, clean_desc=desc_for_embed)

        return record

    def deduplicate(self, records: list[dict[str, object]]) -> list[dict[str, object]]:
        """Khử trùng lặp dựa trên listing_id hoặc id gốc."""
        seen_ids: set[str] = set()
        unique_records: list[dict[str, object]] = []

        for r in records:
            lid = str(r.get("listing_id") or r.get("id") or "")
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                unique_records.append(r)
            elif not lid:
                unique_records.append(r)

        return unique_records

    @staticmethod
    def _has_llm_furniture(
        rep_obj: Optional[ListingExtraction],
        rep: Optional[object],
        record: dict[str, object],
    ) -> bool:
        """Kiểm tra báo cáo LLM / concept_scores có xác nhận phòng có nội thất hay không."""
        if rep_obj and getattr(rep_obj, "amenities", None):
            furn = getattr(rep_obj.amenities, "furniture", None)
            val = getattr(furn, "value", None)
            if str(val or "").strip().lower() == "yes":
                return True

        if isinstance(rep, dict):
            amenities = rep.get("amenities")
            if isinstance(amenities, dict):
                furn = amenities.get("furniture")
                val = furn.get("value") if isinstance(furn, dict) else furn
                if str(val or "").strip().lower() == "yes":
                    return True

        concept_scores = record.get("concept_scores")
        if isinstance(concept_scores, dict):
            amenities_scores = concept_scores.get("amenities")
            if isinstance(amenities_scores, dict):
                score = amenities_scores.get("furniture")
                try:
                    if score is not None and float(score) >= 0.5:
                        return True
                except (TypeError, ValueError):
                    pass

        return False

    def transform(
        self,
        raw_records: list[dict[str, object]],
        llm_reports: Optional[Union[dict[str, object], list[dict[str, object]], str, Path]] = None,
        active_only: bool = False,
    ) -> list[dict[str, object]]:
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

            # Loại bỏ các tin rác thiếu giá/diện tích, tọa độ ngoài VN hoặc ngoài ngưỡng loại phòng
            if not _is_valid_transformed_record(cleaned):
                skipped_invalid += 1
                continue

            # Loại bỏ tin phi nhà ở (kho/xưởng/mặt bằng/ki-ốt/cho thục) hoặc thuê theo ngày/giờ
            clean_title_str = str(cleaned.get("clean_title") or "")
            full_clean_text = f"{clean_title_str}\n{cleaned.get('clean_description') or ''}"
            if _P_NON_RESIDENTIAL_AD.search(clean_title_str) or _P_DAILY_RENTAL.search(full_clean_text):
                skipped_invalid += 1
                continue

            # Lọc nếu chỉ muốn lấy tin active
            if active_only and not cleaned["is_active"]:
                continue

            cleaned_records.append(cleaned)

        if skipped_invalid > 0:
            print(f"[TRANSFORM] Đã loại bỏ {skipped_invalid} bản ghi không hợp lệ (thiếu giá/diện tích, ngoài biên hoặc phi nhà ở).", flush=True)

        # 3. Tùy chọn chạy PriceEvaluator nếu enable_price_evaluator=True
        if self.enable_price_evaluator and cleaned_records:
            try:
                from crawler.model.ml.price_evaluator import PriceEvaluator
                evaluator = PriceEvaluator()
                df_eval = evaluator.evaluate_batch(cleaned_records)
                if not df_eval.empty and "price_score" in df_eval.columns:
                    scores_map = dict(zip(df_eval["listing_id"].astype(str), df_eval["price_score"]))
                    for cr in cleaned_records:
                        lid = str(cr.get("listing_id") or cr.get("id") or "")
                        if lid in scores_map and scores_map[lid] is not None:
                            cr["price_score"] = float(scores_map[lid])
                    print(f"[TRANSFORM] Đã tính toán price_score cho {len(scores_map)} bản ghi qua mô hình ML.", flush=True)
            except Exception as e:
                print(f"[TRANSFORM] Bỏ qua PriceEvaluator tự động: {e}", flush=True)

        print(f"[TRANSFORM] Hoàn tất Transform! Thu được {len(cleaned_records)} bản ghi sạch sẵn sàng nạp CSDL & Embedding.", flush=True)
        return cleaned_records


if __name__ == "__main__":
    import argparse
    import os
    from crawler.config.paths import LLM_CHECKPOINT_PATH, TRANSFORMED_JSONL_PATH
    from crawler.config.settings import GEMINI_API_KEYS
    from crawler.etl.extract import extract_raw_listings
    from crawler.etl.io_utils import read_jsonl, write_jsonl

    parser = argparse.ArgumentParser(description="Chạy Transform độc lập và xuất file trung gian JSONL.")
    parser.add_argument("--input", type=str, default=None, help="File JSONL dữ liệu thô đầu vào (nếu bỏ trống sẽ đọc từ Staging DB)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số bản ghi xử lý")
    parser.add_argument("--all", action="store_true", help="Xử lý toàn bộ dữ liệu trong Staging DB (mặc định chỉ lấy tin chưa xử lý)")
    parser.add_argument("--active-only", action="store_true", help="Chỉ giữ lại tin đang active")
    parser.add_argument("--llm", action="store_true", help="Chạy Gemini LLM trích xuất trước khi Transform")
    parser.add_argument("--checkpoint", type=str, default=None, help="Đường dẫn file báo cáo LLM")
    parser.add_argument("--eval-price", action="store_true", help="Bật PriceEvaluator ML")
    parser.add_argument("--embed", action="store_true", help="Sinh luôn vector embedding E5-base vào file trung gian")
    parser.add_argument(
        "--output",
        type=str,
        default=str(TRANSFORMED_JSONL_PATH),
        help=f"Đường dẫn file trung gian JSONL đầu ra (mặc định: {TRANSFORMED_JSONL_PATH})",
    )
    args = parser.parse_args()

    if args.input:
        raws = read_jsonl(args.input)
        if args.limit is not None:
            raws = raws[: args.limit]
    else:
        raws = extract_raw_listings(unprocessed_only=not args.all, limit=args.limit)

    if not raws:
        print("[TRANSFORM] Không có dữ liệu thô để xử lý.")
    else:
        ckpt_path = args.checkpoint
        if args.llm:
            keys = [k.strip() for k in (GEMINI_API_KEYS or "").split(",") if k.strip()]
            if keys:
                from crawler.model.llm.pipeline import run_pipeline_chunking
                ckpt_p = Path(ckpt_path) if ckpt_path else LLM_CHECKPOINT_PATH
                run_pipeline_chunking(datas=raws, api_keys=keys, checkpoint_path=ckpt_p)
                ckpt_path = str(ckpt_p)
            else:
                print("[TRANSFORM] Cảnh báo: --llm được bật nhưng chưa cấu hình GEMINI_API_KEYS.")
        elif not ckpt_path and os.path.exists(LLM_CHECKPOINT_PATH):
            ckpt_path = str(LLM_CHECKPOINT_PATH)

        transformer = ListingTransformer(llm_reports=ckpt_path, enable_price_evaluator=args.eval_price)
        cleans = transformer.transform(raws, active_only=args.active_only)

        if args.embed and cleans:
            from crawler.etl.embed import ListingEmbedder
            cleans = ListingEmbedder().embed_records(cleans)

        out_path = write_jsonl(args.output, cleans)
        print(f"\n[TRANSFORM] Đã xử lý {len(cleans)}/{len(raws)} bản ghi và lưu file trung gian: {out_path}", flush=True)
        if cleans:
            sample = {
                "listing_id": cleans[0].get("listing_id"),
                "title": cleans[0].get("title"),
                "room_type": cleans[0].get("room_type"),
                "furnishing_code": cleans[0].get("furnishing_code"),
                "embedding_text": (cleans[0].get("embedding_text") or "")[:200] + "...",
            }
            print("Mẫu kết quả:\n", json.dumps(sample, ensure_ascii=False, indent=2))


