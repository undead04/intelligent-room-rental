"""Thin wrapper delegating database loading to Crawler ETL (`crawler.etl.load.DataLoader`).

NOTE: Theo kiến trúc ETL chuẩn, việc nạp dữ liệu & vector embedding vào PostgreSQL
thuộc trách nhiệm của module `crawler` (`python -m crawler.etl.load` — ưu tiên đọc
từ file nhị phân `listings_clean.parquet` tốc độ cao).
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.etl.load import DataLoader


def load_data(input_path: str | None = None) -> tuple[int, int]:
    loader = DataLoader()
    records = loader.read_processed_records(input_path)
    return loader.load_to_postgres(records)


if __name__ == "__main__":
    load_data()
