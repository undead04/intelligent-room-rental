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

def run_pipeline(destinations: list[str] = None, active_only: bool = False, raw_dir: str = None, output_csv: str = None) -> list[dict]:
    """
    Điều phối luồng ETL toàn diện:
    1. EXTRACT: Đọc toàn bộ file JSON thô
    2. TRANSFORM: Làm sạch, khử trùng lặp, chuẩn hóa kiểu
    3. LOAD: Nạp vào các đích đến (CSV, Parquet, PostgreSQL)
    
    Returns:
        list[dict]: Danh sách các bản ghi đã làm sạch.
    """
    if destinations is None:
        destinations = ["csv"]

    print("\n" + "#" * 60, flush=True)
    print("     KHỞI ĐỘNG PIPELINE ETL (EXTRACT - TRANSFORM - LOAD)", flush=True)
    print("#" * 60 + "\n", flush=True)

    # 1. EXTRACT
    raw_records = extract_raw_listings(raw_dir=raw_dir)
    if not raw_records:
        print("[ETL] Không có dữ liệu thô để xử lý. Dừng pipeline.", flush=True)
        return []

    # 2. TRANSFORM
    transformer = ListingTransformer()
    cleaned_records = transformer.transform(raw_records, active_only=active_only)
    if not cleaned_records:
        print("[ETL] Không có dữ liệu hợp lệ sau khi Transform. Dừng pipeline.", flush=True)
        return []

    # 3. LOAD
    loader = DataLoader()
    if "csv" in destinations:
        loader.load_to_csv(cleaned_records, output_path=output_csv)

    if "parquet" in destinations:
        loader.load_to_parquet(cleaned_records)

    if "db" in destinations or "postgres" in destinations:
        loader.load_to_postgres(cleaned_records)

    # Báo cáo thống kê
    loader.print_summary(cleaned_records)
    return cleaned_records

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL Pipeline Runner cho dữ liệu phòng trọ")
    parser.add_argument(
        "--dest",
        nargs="+",
        default=["csv"],
        choices=["csv", "parquet", "db", "postgres"],
        help="Các đích đến muốn nạp dữ liệu: 'csv', 'parquet', 'db'."
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Chỉ lấy những tin đang hoạt động (is_active == True)."
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

    args = parser.parse_args()
    run_pipeline(
        destinations=args.dest,
        active_only=args.active_only,
        raw_dir=args.raw_dir,
        output_csv=args.output_csv
    )
