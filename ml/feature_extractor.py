"""
ml/feature_extractor.py
Trích xuất đặc trưng (Feature Extraction) chuẩn hóa từ datas.json hoặc DB
cho mô hình định giá phòng trọ ML.

Đặc tả:
- Loại bỏ hoàn toàn các feature cũ không còn trong Schema chuẩn (ví dụ: water_heater, wifi).
- Giữ các tiện ích chuẩn hóa (private_wc, aircon, mezzanine, kitchen, washing_machine,
  window_balcony, furniture, parking) cùng quy định & an ninh cốt lõi (free_hours,
  no_shared_landlord, fingerprint_lock, camera, guard).
- Làm sạch và lọc nhiễu ngoại lai (outliers) về giá, diện tích và tọa độ địa lý TP.HCM.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET_PATH = PROJECT_ROOT / "crawler" / "data" / "processed" / "listings_clean.parquet"
DEFAULT_DATA_PATH = (
    DEFAULT_PARQUET_PATH
    if DEFAULT_PARQUET_PATH.exists()
    else PROJECT_ROOT / "backend" / "app" / "datas" / "datas.json"
)

# Danh sách tiện ích / quy định / an ninh chuẩn hóa theo Schema mới (KHÔNG có water_heater, wifi)
CANONICAL_AMENITY_KEYS = [
    "private_wc",
    "aircon",
    "mezzanine",
    "kitchen",
    "washing_machine",
    "window_balcony",
    "furniture",
    "parking",
]

CANONICAL_RULE_KEYS = [
    "free_hours",
    "no_shared_landlord",
]

CANONICAL_SAFETY_KEYS = [
    "fingerprint_lock",
    "camera",
    "guard",
    "safe_area",
]

ALL_BINARY_KEYS = CANONICAL_AMENITY_KEYS + CANONICAL_RULE_KEYS + CANONICAL_SAFETY_KEYS


def extract_features_from_record(r: dict[str, Any]) -> dict[str, Any]:
    """Chuyển 1 record thô thành vector feature dict cho ML."""
    row = {
        "listing_id": str(r.get("listing_id") or r.get("id") or ""),
        "area_m2": float(r.get("area_m2") or 0.0),
        "lat": float(r.get("lat") or 0.0),
        "lng": float(r.get("lng") or 0.0),
        "price_vnd": float(r.get("price_vnd") or 0.0),
        "furnishing_code": float(r.get("furnishing_code") or 2.0), # 2: chưa nội thất (default)
    }

    # Đọc từ concept_scores hoặc lồng trong report (hỗ trợ cả dict lẫn JSON string từ Parquet)
    concept = r.get("concept_scores") or {}
    if isinstance(concept, str) and concept.strip().startswith("{"):
        try:
            concept = json.loads(concept)
        except Exception:
            concept = {}

    report = r.get("report") or {}
    if isinstance(report, str) and report.strip().startswith("{"):
        try:
            report = json.loads(report)
        except Exception:
            report = {}

    rep_amenities = report.get("amenities") or {}
    rep_rules = report.get("rules") or {}
    rep_safety = report.get("safety") or {}

    for k in ALL_BINARY_KEYS:
        val = 0
        # 1. Thử đọc từ concept_scores (điểm >= 0.8 coi như có)
        if k in concept:
            val = 1 if float(concept[k]) >= 0.8 else 0
        # 2. Hoặc đọc từ report (Signal value == 'yes')
        elif k in rep_amenities:
            sig = rep_amenities[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0
        elif k in rep_rules:
            sig = rep_rules[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0
        elif k in rep_safety:
            sig = rep_safety[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0

        row[f"is_{k}"] = int(val)

    return row


def load_and_preprocess_dataset(
    data_path: str | Path = DEFAULT_DATA_PATH,
    min_area: float = 8.0,
    max_area: float = 150.0,
    min_price: float = 500_000.0,
    max_price: float = 25_000_000.0,
    min_ppm: float = 30_000.0,
    max_ppm: float = 600_000.0,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Nạp dataset từ Parquet (ưu tiên) hoặc JSON, loại bỏ nhiễu và trả về (X, y)."""
    path_obj = Path(data_path)
    if not path_obj.exists() and DEFAULT_PARQUET_PATH.exists():
        path_obj = DEFAULT_PARQUET_PATH

    if path_obj.suffix.lower() == ".parquet":
        raw_df = pd.read_parquet(path_obj)
        raw_data = raw_df.to_dict(orient="records")
    else:
        with open(path_obj, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    extracted_rows = [extract_features_from_record(r) for r in raw_data]
    df = pd.DataFrame(extracted_rows)

    # 1. Lọc bản ghi hợp lệ về tọa độ trong khu vực TP.HCM
    # Bounding box TP.HCM: lat [10.3, 11.2], lng [106.3, 107.1]
    df = df[
        (df["lat"] >= 10.3)
        & (df["lat"] <= 11.2)
        & (df["lng"] >= 106.3)
        & (df["lng"] <= 107.1)
    ]

    # 2. Lọc diện tích và giá hợp lệ
    df = df[(df["area_m2"] >= min_area) & (df["area_m2"] <= max_area)]
    df = df[(df["price_vnd"] >= min_price) & (df["price_vnd"] <= max_price)]

    # 3. Lọc đơn giá m2 (PPM: Price Per M2) để loại tin ảo, tin ở ghép chia đầu người hoặc nhầm số 0
    ppm = df["price_vnd"] / df["area_m2"]
    df = df[(ppm >= min_ppm) & (ppm <= max_ppm)].copy()

    df = df.reset_index(drop=True)
    y = df["price_vnd"].copy()
    X = df.drop(columns=["listing_id", "price_vnd"]).copy()

    return X, y


if __name__ == "__main__":
    X, y = load_and_preprocess_dataset()
    print("Preprocessed X shape:", X.shape)
    print("Features:", X.columns.tolist())
    print("Target y summary:\n", y.describe())
