"""
Unit Tests cho các thành phần toán học trong crawler/model/ml/models.py.
Kiểm tra:
1. make_base_features: Sinh đặc trưng phái sinh và khử tương quan.
2. SpatialTE: Trọng số nghịch đảo khoảng cách IDW ưu tiên láng giềng gần hơn.
3. Persistence: Serialize và Deserialize InputGuard + MondrianPriceInterval qua joblib.

(Các kịch bản QA tổng thể, chống rò rỉ target và kiểm định DB được bao trọn độc lập
bởi crawler/tests/test_ml_v2_qa_independent.py).
"""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from crawler.model.ml.models import (
    InputGuard,
    MondrianPriceInterval,
    SpatialTE,
    make_base_features,
)


def _make_sample_df(n: int = 30, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "area_m2": rng.uniform(15.0, 45.0, size=n),
        "lat": rng.uniform(10.72, 10.85, size=n),
        "lng": rng.uniform(106.62, 106.75, size=n),
        "room_type_id": rng.choice([1, 2, 3, 4, 5], size=n),
        "furnishing_code": rng.choice([1, 2, 3], size=n),
        "amenity_overall": rng.uniform(2.5, 4.5, size=n),
        "safety_score": rng.uniform(2.5, 4.5, size=n),
        "dist_nearest_hub_km": rng.uniform(0.5, 8.0, size=n),
        "dist_nearest_uni_km": rng.uniform(0.3, 5.0, size=n),
        "is_ac": rng.integers(0, 2, size=n),
        "is_private_wc": rng.integers(0, 2, size=n),
        "is_wifi": np.ones(n, dtype=int),
    })
    y = pd.Series(
        2_000_000 + df["area_m2"] * 120_000 + df["amenity_overall"] * 300_000 + rng.normal(0, 150_000, size=n)
    )
    return df, y


def test_make_base_features_decorrelated():
    """Kiểm tra make_base_features sinh đúng cột phái sinh và loại bỏ cột đa cộng tuyến."""
    df, _ = _make_sample_df(10)
    out = make_base_features(df)

    assert "amenity_density" in out.columns
    assert "lat_lng_sum" in out.columns
    assert "lat_lng_diff" in out.columns
    # Không sinh các cột đa cộng tuyến thừa
    assert "log_area" not in out.columns
    assert "n_amenities" not in out.columns


def test_spatial_te_inverse_distance_weighting():
    """Kiểm tra SpatialTE trọng số nghịch đảo khoảng cách ưu tiên láng giềng gần hơn."""
    # Tạo 1 điểm trung tâm (10.77, 106.65) và 5 điểm láng giềng:
    # - 1 điểm cực gần (cùng tọa độ) giá 3 triệu
    # - 4 điểm cách xa (~15 km) giá 10 triệu
    X_fit = pd.DataFrame({
        "lat": [10.7700, 10.9000, 10.9010, 10.9020, 10.9030, 10.9040],
        "lng": [106.6500, 106.7500, 106.7510, 106.7520, 106.7530, 106.7540],
        "area_m2": [25.0] * 6,
    })
    y_fit = pd.Series([3_000_000.0] + [10_000_000.0] * 5)

    te = SpatialTE(ks=(5,)).fit(X_fit, y_fit)
    X_query = pd.DataFrame({"lat": [10.7701], "lng": [106.6501], "area_m2": [25.0]})
    res = te.transform(X_query)

    assert "nb5_logy_mean" in res.columns
    assert "nb5_logppm_mean" in res.columns
    assert "nb5_dist_km" in res.columns
    assert "nb5_logppm_med" not in res.columns

    # Trung bình không trọng số của 1 điểm 3tr và 4 điểm 10tr trong log space:
    unweighted_mean = (np.log1p(3_000_000.0) + 4 * np.log1p(10_000_000.0)) / 5.0
    # Với trọng số nghịch đảo khoảng cách, giá trị dự đoán phải nghiêng mạnh về phía 3tr (< unweighted_mean)
    assert res["nb5_logy_mean"].iloc[0] < unweighted_mean


def test_models_joblib_persistence(tmp_path: Path):
    """Kiểm tra lưu và nạp lại InputGuard + MondrianPriceInterval qua joblib."""
    df, y = _make_sample_df(120)
    guard = InputGuard().fit(df)

    fake_lgb_res = {
        "best_params": {
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_child_samples": 5,
            "verbose": -1,
            "n_jobs": 1,
            "seed": 42,
        }
    }
    pi = MondrianPriceInterval(fake_lgb_res, n_bins=2, min_bin=10, coverage=0.8, seed=42).fit(df, y)

    guard_file = tmp_path / "guard.joblib"
    pi_file = tmp_path / "pi.joblib"
    joblib.dump(guard, guard_file)
    joblib.dump(pi, pi_file)

    loaded_guard = joblib.load(guard_file)
    loaded_pi = joblib.load(pi_file)

    sample = df.iloc[:5].copy()
    sample_prices = y.iloc[:5].to_numpy()

    pd.testing.assert_frame_equal(guard.check(sample, sample_prices), loaded_guard.check(sample, sample_prices))
    pd.testing.assert_frame_equal(pi.predict(sample), loaded_pi.predict(sample))
