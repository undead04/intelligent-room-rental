import os
import sys
import json

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.staging_db import staging_db

DEFAULT_RAW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "listings"))

def extract_raw_listings(
    unprocessed_only: bool = False,
    source: str = None,
    limit: int = None,
    raw_dir: str = None,
) -> list[dict]:
    """
    [EXTRACT STAGE]
    Đọc dữ liệu thô từ SQLite Staging Database (crawler/data/raw/staging.db).
    Hỗ trợ Incremental Extraction (chỉ trích xuất các tin mới cào chưa qua ETL: unprocessed_only=True).
    Hỗ trợ fallback đọc các file JSON lẻ nếu có chỉ định thư mục legacy raw_dir.
    
    Returns:
        list[dict]: Danh sách các bản ghi JSON thô.
    """
    # 1. Ưu tiên đọc từ SQLite Staging DB (chuẩn kiến trúc Two-Tier Storage)
    if os.path.exists(staging_db.db_path):
        mode_str = "tin MỚI chưa qua ETL" if unprocessed_only else "TOÀN BỘ tin"
        source_str = f" [Nguồn: {source}]" if source else ""
        print(f"[EXTRACT] Đang đọc {mode_str}{source_str} từ SQLite Staging DB: {staging_db.db_path}...", flush=True)
        
        records = staging_db.get_raw_listings(
            unprocessed_only=unprocessed_only,
            source=source,
            limit=limit,
        )
        print(f"[EXTRACT] Hoàn tất! Đã trích xuất thành công {len(records)} bản ghi từ Staging DB.", flush=True)
        if records:
            return records

    # 2. Fallback: Nếu Staging DB chưa có dữ liệu và có thư mục JSON lẻ cũ
    target_dir = raw_dir or DEFAULT_RAW_DIR
    if os.path.exists(target_dir):
        files = sorted([f for f in os.listdir(target_dir) if f.endswith(".json")])
        if files:
            print(f"[EXTRACT] Fallback đọc {len(files)} file JSON thô từ thư mục: {target_dir}", flush=True)
            raw_records = []
            for fname in files:
                fpath = os.path.join(target_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            raw_records.append(data)
                except Exception as e:
                    pass
            print(f"[EXTRACT] Hoàn tất fallback! Đã đọc {len(raw_records)} bản ghi.", flush=True)
            return raw_records

    print("[EXTRACT] Không tìm thấy dữ liệu thô trong Staging DB hoặc thư mục dữ liệu.", flush=True)
    return []

if __name__ == "__main__":
    records = extract_raw_listings()
    print(f"Tổng số bản ghi trích xuất: {len(records)}")
