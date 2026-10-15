import os
import sys
import argparse

# Tự động điều chỉnh encoding cho stdout trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.etl.extract import extract_raw_listings
from crawler.etl.transform import ListingTransformer
from crawler.etl.load import DataLoader
from crawler.staging_db import staging_db

def run_pipeline(
    destinations: list[str] = None,
    active_only: bool = False,
    unprocessed_only: bool = False,
    embed: bool = False,
    raw_dir: str = None,
    output_csv: str = None,
    output_json: str = None,
    checkpoint_path: str = None,
) -> list[dict]:
    """
    Điều phối luồng ETL toàn diện:
    1. EXTRACT: Đọc dữ liệu từ SQLite Staging DB (hỗ trợ incremental)
    2. TRANSFORM: Làm sạch, khử trùng lặp, chuẩn hóa kiểu, tích hợp LLM báo cáo & embedding_text
    3. EMBED: Sinh vector offline với intfloat/multilingual-e5-base
    4. LOAD: Nạp vào các đích đến (CSV, JSON, Parquet, PostgreSQL)
    5. MARK: Đánh dấu is_processed = 1 trong Staging DB
    
    Returns:
        list[dict]: Danh sách các bản ghi đã làm sạch.
    """
    if destinations is None:
        destinations = ["csv"]

    print("\n" + "#" * 60, flush=True)
    print("     KHỞI ĐỘNG PIPELINE ETL (EXTRACT - TRANSFORM - LOAD)", flush=True)
    print("#" * 60 + "\n", flush=True)

    # 1. EXTRACT
    raw_records = extract_raw_listings(
        unprocessed_only=unprocessed_only,
        raw_dir=raw_dir,
    )
    if not raw_records:
        print("[ETL] Không có dữ liệu thô để xử lý. Dừng pipeline.", flush=True)
        return []

    # 2. TRANSFORM
    transformer = ListingTransformer(llm_reports=checkpoint_path)
    cleaned_records = transformer.transform(raw_records, active_only=active_only)
    if not cleaned_records:
        print("[ETL] Không có dữ liệu hợp lệ sau khi Transform. Dừng pipeline.", flush=True)
        return []

    # 3. EMBED (Sinh vector ngữ nghĩa bằng multilingual-e5-base)
    if embed or ("db" in destinations or "postgres" in destinations):
        from crawler.etl.embed import ListingEmbedder
        embedder = ListingEmbedder()
        cleaned_records = embedder.embed_records(cleaned_records)

    # 4. LOAD
    loader = DataLoader()
    if "csv" in destinations:
        loader.load_to_csv(cleaned_records, output_path=output_csv)

    if "json" in destinations:
        loader.load_to_json(cleaned_records, output_path=output_json)

    if "parquet" in destinations:
        loader.load_to_parquet(cleaned_records)

    if "db" in destinations or "postgres" in destinations:
        loader.load_to_postgres(cleaned_records)

    # 4. MARK PROCESSED IN STAGING DB
    processed_ids = [r.get("listing_id") for r in cleaned_records if r.get("listing_id")]
    if processed_ids:
        updated = staging_db.mark_as_processed(processed_ids)
        print(f"[ETL] Đã cập nhật trạng thái is_processed = 1 cho {updated} tin trong Staging DB.", flush=True)

    # Báo cáo thống kê
    loader.print_summary(cleaned_records)
    return cleaned_records

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL Pipeline Runner cho dữ liệu phòng trọ")
    parser.add_argument(
        "--dest",
        nargs="+",
        default=["csv"],
        choices=["csv", "json", "parquet", "db", "postgres"],
        help="Các đích đến muốn nạp dữ liệu: 'csv', 'json', 'parquet', 'db'."
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Chỉ lấy những tin đang hoạt động (is_active == True)."
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Chế độ Incremental: Chỉ xử lý các tin MỚI chưa qua ETL (is_processed == 0)."
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Tự động sinh vector embedding bằng multilingual-e5-base trước khi nạp.",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default=None,
        help="Đường dẫn thư mục chứa raw JSON (tùy chọn)."
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Đường dẫn file CSV xuất ra (tùy chọn)."
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Đường dẫn file JSON xuất ra (tùy chọn)."
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Đường dẫn file checkpoint chứa báo cáo trích xuất LLM (tùy chọn)."
    )

    args = parser.parse_args()
    run_pipeline(
        destinations=args.dest,
        active_only=args.active_only,
        unprocessed_only=args.incremental,
        embed=args.embed,
        raw_dir=args.raw_dir,
        output_csv=args.output_csv,
        output_json=args.output_json,
        checkpoint_path=args.checkpoint,
    )
