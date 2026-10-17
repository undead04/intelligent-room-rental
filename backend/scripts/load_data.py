"""Thin wrapper delegating database loading to Crawler ETL (`crawler.etl.load.DataLoader`).

NOTE: Theo kiến trúc ETL chuẩn, việc nạp dữ liệu & vector embedding vào PostgreSQL
thuộc trách nhiệm của module `crawler` (`python -m crawler.etl.load` hoặc
`python -m crawler.etl.pipeline --dest db --embed --eval-price`).
File này chỉ giữ lại để tương thích ngược, gọi thẳng sang `crawler.etl.load.DataLoader`.
"""
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.etl.load import DataLoader


def load_data(input_path: str | None = None) -> tuple[int, int]:
    processed_dir = os.path.join(PROJECT_ROOT, "crawler", "data", "processed")
    if not input_path:
        datas_json = os.path.join(processed_dir, "datas.json")
        clean_json = os.path.join(processed_dir, "listings_clean.json")
        input_path = datas_json if os.path.exists(datas_json) else clean_json

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy dữ liệu đã qua ETL tại: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    loader = DataLoader()
    return loader.load_to_postgres(records)


if __name__ == "__main__":
    load_data()
