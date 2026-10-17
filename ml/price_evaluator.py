"""
ml/price_evaluator.py
Bộ thẩm định & chấm điểm giá phòng trọ (Price Evaluator).

Cung cấp interface suy luận (Inference Service) dùng chung cho:
1. ETL Transformer (crawler/etl/transform.py)
2. FastAPI Backend
3. Batch update dữ liệu (datas.json / Database)
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd

from ml.feature_extractor import extract_features_from_record
from ml.models import (
    MondrianPriceInterval,
    PriceInterval,
    SpatialTE,
    attach,
    blend_predict,
    make_base_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPELINE_PATH = PROJECT_ROOT / "ml" / "artifacts" / "rent_pipeline.joblib"
DEFAULT_GUARD_PATH = PROJECT_ROOT / "ml" / "artifacts" / "guard.joblib"


class PriceEvaluator:
    """Class suy luận thẩm định giá và tính điểm price_score."""

    def __init__(
        self,
        pipeline_path: str | Path = DEFAULT_PIPELINE_PATH,
        guard_path: str | Path = DEFAULT_GUARD_PATH,
    ):
        p_path = Path(pipeline_path)
        if not p_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file model pipeline tại: {p_path}. Hãy chạy train_price_model.py trước.")

        bundle = joblib.load(p_path)
        self.results = bundle["results"]
        self.interval = bundle["interval"]
        self.features_in = bundle["features_in"]

        self.guard = None
        g_path = Path(guard_path)
        if g_path.exists():
            try:
                self.guard = joblib.load(g_path)
            except Exception:
                self.guard = None

    def evaluate_batch(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        """Đánh giá hàng loạt danh sách records và trả về DataFrame kết quả."""
        if not records:
            return pd.DataFrame()

        # 1. Trích xuất features
        extracted = [extract_features_from_record(r) for r in records]
        df_feat = pd.DataFrame(extracted)

        prices = df_feat["price_vnd"].to_numpy(dtype=float)
        # Giữ đúng các cột và thứ tự khi train
        X_in = df_feat[[c for c in self.features_in if c in df_feat.columns]].copy()
        for c in self.features_in:
            if c not in X_in.columns:
                X_in[c] = 0

        X_in = X_in[self.features_in]

        # 2. Dự đoán khoảng giá (low, high) và giá kỳ vọng blend (mid)
        rng = self.interval.predict(X_in)
        lows = rng["low"].to_numpy(dtype=float)
        highs = rng["high"].to_numpy(dtype=float)

        mids = blend_predict(self.results, X_in, smear=True)
        mids = np.clip(mids, lows, highs)

        # 3. Tính độ lệch z-score trong không gian log và điểm price_score [0, 100]
        llo, lhi = np.log1p(lows), np.log1p(highs)
        center = (llo + lhi) / 2.0
        half = np.maximum((lhi - llo) / 2.0, 1e-6)

        # Safe log price
        safe_prices = np.clip(prices, 1.0, None)
        z = (np.log1p(safe_prices) - center) / half

        # score: 50 - 25*z (100 = cực rẻ/hời, 50 = sát trung tâm giá thị trường, 0 = rất đắt)
        scores_100 = np.clip(50.0 - 25.0 * z, 0.0, 100.0)
        # Chuẩn hóa về [0.0, 1.0] cho DB và Hybrid MCDM Rerank
        price_scores = np.round(scores_100 / 100.0, 3)

        # 4. Phân loại nhận định (Verdict)
        conditions = [z < -1.5, z < -1.0, z <= 1.0, z <= 1.5]
        choices = [
            "Rất rẻ so với thị trường",
            "Rẻ hơn thị trường",
            "Hợp lý",
            "Đắt hơn thị trường",
        ]
        verdicts = np.select(conditions, choices, default="Rất đắt so với thị trường")

        # 5. Kiểm tra InputGuard
        status_col = ["ok"] * len(records)
        if self.guard is not None:
            try:
                g_df = self.guard.check(X_in, prices)
                status_col = g_df["status"].tolist()
            except Exception:
                pass

        results_df = pd.DataFrame({
            "listing_id": df_feat["listing_id"],
            "price_vnd": prices,
            "price_low": np.round(lows, 0),
            "price_mid": np.round(mids, 0),
            "price_high": np.round(highs, 0),
            "z_score": np.round(z, 2),
            "price_score_100": np.round(scores_100, 1),
            "price_score": price_scores,
            "verdict": verdicts,
            "guard_status": status_col,
        })

        return results_df

    def evaluate_single(self, record: dict[str, Any]) -> dict[str, Any]:
        """Đánh giá 1 bài đăng duy nhất."""
        df_res = self.evaluate_batch([record])
        if df_res.empty:
            return {}
        return df_res.iloc[0].to_dict()


# Alias đồng bộ tên class dùng trong tài liệu và crawler/model/ml
RoomPriceEvaluator = PriceEvaluator

