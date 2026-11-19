import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Đảm bảo root dự án có trong sys.path khi chạy file độc lập
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from crawler.config.paths import RAW_EXTRACT_JSONL_PATH
from crawler.etl.io_utils import write_jsonl
from crawler.staging_db import staging_db


def extract_raw_listings(
    unprocessed_only: bool = False,
    source: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    [EXTRACT STAGE]
    Đọc dữ liệu thô từ SQLite Staging Database (crawler/data/raw/staging.db).
    Hỗ trợ Incremental Extraction (chỉ trích xuất các tin mới cào chưa qua ETL: unprocessed_only=True).
    
    Returns:
        list[dict]: Danh sách các bản ghi JSON thô.
    """
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

    print("[EXTRACT] Không tìm thấy dữ liệu thô trong Staging DB.", flush=True)
    return []


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Trích xuất dữ liệu thô từ Staging Database ra file trung gian JSONL.")
    parser.add_argument("--limit", type=int, default=None, help="Số lượng tin tối đa cần trích xuất (mặc định: tất cả)")
    parser.add_argument("--unprocessed-only", action="store_true", help="Chỉ trích xuất tin chưa xử lý")
    parser.add_argument("--source", type=str, default=None, help="Nguồn crawl (ví dụ: nhatot, phongtro123)")
    parser.add_argument(
        "--output",
        type=str,
        default=str(RAW_EXTRACT_JSONL_PATH),
        help=f"Đường dẫn file trung gian JSONL đầu ra (mặc định: {RAW_EXTRACT_JSONL_PATH})",
    )
    args = parser.parse_args()

    records = extract_raw_listings(
        unprocessed_only=args.unprocessed_only,
        source=args.source,
        limit=args.limit,
    )
    print(f"\n[EXTRACT] Trích xuất thành công {len(records)} tin đăng.", flush=True)
    if records and args.output:
        out_path = write_jsonl(args.output, records)
        print(f"[EXTRACT] Đã ghi file trung gian tại: {out_path}", flush=True)
    if records:
        sample = {
            "listing_id": records[0].get("listing_id"),
            "title": records[0].get("title"),
            "price_vnd": records[0].get("price_vnd"),
            "area_m2": records[0].get("area_m2"),
            "district": records[0].get("district"),
            "city": records[0].get("city"),
        }
        print("Mẫu tin đầu tiên:\n", json.dumps(sample, ensure_ascii=False, indent=2))
