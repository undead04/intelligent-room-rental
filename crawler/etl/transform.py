import os
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
        if rep:
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
                if getattr(rep_obj, "numeric", None):
                    if rep_obj.numeric.bedrooms is not None:
                        record["num_bedrooms"] = rep_obj.numeric.bedrooms
                    if rep_obj.numeric.bathrooms is not None:
                        record["num_bathrooms"] = rep_obj.numeric.bathrooms
            elif isinstance(rep, dict):
                record["safety_score"] = self.clean_number(rep.get("safety_score"), default=None)
                record["amenity_overall"] = self.clean_number(rep.get("amenity_overall_score") or rep.get("amenity_overall"), default=None)
                record["concept_scores"] = rep.get("concept_scores")
                record["report"] = rep
                num_dict = rep.get("numeric") or {}
                if isinstance(num_dict, dict):
                    if num_dict.get("bedrooms") is not None:
                        record["num_bedrooms"] = num_dict.get("bedrooms")
                    if num_dict.get("bathrooms") is not None:
                        record["num_bathrooms"] = num_dict.get("bathrooms")
        else:
            record["safety_score"] = self.clean_number(record.get("safety_score"), default=None)
            record["amenity_overall"] = self.clean_number(record.get("amenity_overall"), default=None)
            record["concept_scores"] = record.get("concept_scores")

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

        record["room_type"] = norm_code
        record["room_type_id"] = ROOM_TYPE_CODE_TO_ID[norm_code]

        # 10. Giữ price_score (nếu đã có thì giữ nguyên, ngược lại để None chờ ML định giá)
        record["price_score"] = self.clean_number(record.get("price_score"), default=None)

        # 10. Tạo chuỗi văn bản giàu ngữ cảnh cho mô hình Embedding
        extracted_data = extract_room_data_from_record(record, rep)
        desc_for_embed = f"{clean_title}\n{clean_desc}".strip()
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
    import json
    from crawler.etl.extract import extract_raw_listings

    parser = argparse.ArgumentParser(description="Chạy Transform làm sạch dữ liệu.")
    parser.add_argument("--limit", type=int, default=5, help="Số bản ghi test")
    parser.add_argument("--checkpoint", type=str, default=None, help="Đường dẫn file báo cáo LLM")
    parser.add_argument("--eval-price", action="store_true", help="Bật PriceEvaluator ML")
    args = parser.parse_args()

    raws = extract_raw_listings(limit=args.limit)
    if not raws:
        print("[TRANSFORM] Không có dữ liệu thô trong Staging DB.")
    else:
        transformer = ListingTransformer(llm_reports=args.checkpoint, enable_price_evaluator=args.eval_price)
        cleans = transformer.transform(raws)
        print(f"\n[TRANSFORM DEMO] Đã xử lý {len(cleans)}/{len(raws)} bản ghi.")
        if cleans:
            sample = {
                "listing_id": cleans[0].get("listing_id"),
                "title": cleans[0].get("title"),
                "room_type": cleans[0].get("room_type"),
                "embedding_text": (cleans[0].get("embedding_text") or "")[:200] + "...",
            }
            print("Mẫu kết quả:\n", json.dumps(sample, ensure_ascii=False, indent=2))


