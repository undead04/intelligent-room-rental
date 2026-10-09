import os
import sys
import re
from datetime import datetime

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class ListingTransformer:
    """
    [TRANSFORM STAGE]
    Chịu trách nhiệm làm sạch, chuẩn hóa kiểu dữ liệu, khử trùng lặp
    và trích xuất đặc trưng (feature engineering) từ dữ liệu thô.
    
    >>> Bạn có thể dán (paste) thêm các hàm xử lý từ Colab vào class này.
    """

    def __init__(self):
        pass

    def clean_number(self, value, default=0.0):
        """Ép kiểu số an toàn"""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def clean_record(self, item: dict) -> dict:
        """
        Chuẩn hóa từng bản ghi:
        - Ép kiểu giá (VNĐ), diện tích (m2), tiền cọc
        - Chuẩn hóa tọa độ lat, lng
        - Chuẩn hóa trạng thái is_active, status
        - Ghép mảng images thành chuỗi
        """
        record = dict(item)

        # 1. Trạng thái hoạt động
        if "is_active" not in record:
            record["is_active"] = True
        else:
            record["is_active"] = bool(record["is_active"])

        record["status"] = str(record.get("status") or "active").lower()
        if not record.get("last_checked_at"):
            record["last_checked_at"] = record.get("crawled_at") or datetime.now().isoformat()

        # 2. Số điện thoại (nếu có)
        record["phone"] = str(record.get("phone") or "").strip()

        # 3. Chuẩn hóa số học (Dùng cho ML Model)
        record["price_vnd"] = self.clean_number(record.get("price_vnd"))
        record["area_m2"] = self.clean_number(record.get("area_m2"))
        record["price_million_per_m2"] = self.clean_number(record.get("price_million_per_m2"))
        record["deposit"] = self.clean_number(record.get("deposit"))

        lat = self.clean_number(record.get("lat"), default=None)
        lng = self.clean_number(record.get("lng"), default=None)
        record["lat"] = lat
        record["lng"] = lng

        # 4. Chuẩn hóa hình ảnh (nếu là list thì nối bằng '|')
        if isinstance(record.get("images"), list):
            record["images"] = "|".join(record["images"])

        # 5. [HOOK DÀNH CHO CODE TỪ COLAB]:
        # Bạn có thể gọi thêm các hàm trích xuất tiện ích / NLP / embedding ở đây
        record = self.enrich_features_hook(record)

        return record

    def enrich_features_hook(self, record: dict) -> dict:
        """
        [HOOK / PLACEHOLDER]: Nơi tích hợp code từ Google Colab
        Ví dụ:
        - Tính khoảng cách tới trung tâm (Haversine distance)
        - Trích xuất tiện ích / an ninh từ description
        - Tính điểm MatchScore sơ bộ
        """
        # (Chỗ này để dán code transform nâng cao từ Colab về)
        return record

    def deduplicate(self, records: list[dict]) -> list[dict]:
        """Khử trùng lặp dựa trên listing_id hoặc id gốc"""
        seen_ids = set()
        unique_records = []

        for r in records:
            lid = r.get("listing_id")
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                unique_records.append(r)

        return unique_records

    def transform(self, raw_records: list[dict], active_only: bool = False) -> list[dict]:
        """
        Chạy toàn bộ quy trình Transform:
        1. Khử trùng lặp
        2. Chuẩn hóa từng bản ghi
        3. Lọc bỏ các bản ghi không hợp lệ (giá <= 0 hoặc diện tích <= 0)
        4. Tùy chọn chỉ lấy tin đang active
        """
        print(f"[TRANSFORM] Bắt đầu xử lý {len(raw_records)} bản ghi thô...", flush=True)

        # 1. Khử trùng lặp
        deduped = self.deduplicate(raw_records)
        print(f"[TRANSFORM] Sau khi khử trùng lặp: còn {len(deduped)} bản ghi.", flush=True)

        cleaned_records = []
        skipped_invalid = 0

        for r in deduped:
            cleaned = self.clean_record(r)

            # Loại bỏ các tin rác không có giá hoặc diện tích
            if cleaned["price_vnd"] <= 0 and cleaned["area_m2"] <= 0:
                skipped_invalid += 1
                continue

            # Lọc nếu chỉ muốn lấy tin active
            if active_only and not cleaned["is_active"]:
                continue

            cleaned_records.append(cleaned)

        if skipped_invalid > 0:
            print(f"[TRANSFORM] Đã loại bỏ {skipped_invalid} bản ghi không hợp lệ (thiếu giá & diện tích).", flush=True)

        print(f"[TRANSFORM] Hoàn tất Transform! Thu được {len(cleaned_records)} bản ghi sạch.", flush=True)
        return cleaned_records

if __name__ == "__main__":
    from crawler.etl.extract import extract_raw_listings
    raws = extract_raw_listings()
    transformer = ListingTransformer()
    cleans = transformer.transform(raws)
    print(f"Bản ghi mẫu đầu tiên: {cleans[0]['title']} - Giá: {cleans[0]['price_vnd']} VNĐ")
