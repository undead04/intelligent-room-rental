"""
ml/apply_price_scores.py
Script cập nhật trường price_score vào file datas.json và cơ sở dữ liệu.
"""

import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.price_evaluator import PriceEvaluator
DATA_PATH = PROJECT_ROOT / "backend" / "app" / "datas" / "datas.json"


def apply_scores_to_datas_json(data_path: Path = DATA_PATH):
    print(f"[APPLY] Đang đọc dữ liệu từ: {data_path}...")
    with open(data_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"[APPLY] Khởi tạo PriceEvaluator...")
    evaluator = PriceEvaluator()

    print(f"[APPLY] Đang tính toán price_score cho {len(records)} bản ghi...")
    df_scores = evaluator.evaluate_batch(records)

    scores_map = {
        row["listing_id"]: {
            "price_score": float(row["price_score"]),
            "price_low": float(row["price_low"]),
            "price_mid": float(row["price_mid"]),
            "price_high": float(row["price_high"]),
            "verdict": row["verdict"],
        }
        for _, row in df_scores.iterrows()
    }

    updated_count = 0
    for r in records:
        lid = str(r.get("listing_id") or r.get("id") or "")
        if lid in scores_map:
            val = scores_map[lid]
            r["price_score"] = val["price_score"]
            # Lưu thêm metadata định giá hữu ích
            r["price_evaluation"] = {
                "low": val["price_low"],
                "mid": val["price_mid"],
                "high": val["price_high"],
                "verdict": val["verdict"],
            }
            updated_count += 1

    print(f"[APPLY] Đã gán thành công price_score cho {updated_count}/{len(records)} bản ghi.")
    print("\n--- Phân phối nhận định định giá thị trường ---")
    print(df_scores["verdict"].value_counts(normalize=True).round(3))

    print("\n--- Thống kê điểm price_score [0.0 - 1.0] ---")
    print(df_scores["price_score"].describe())

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n[SUCCESS] Đã lưu file dữ liệu cập nhật tại: {data_path}")


if __name__ == "__main__":
    apply_scores_to_datas_json()
