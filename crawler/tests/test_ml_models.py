"""
Black-box Unit Tests cho crawler/model/ml/models.py (Milestone 2 - FEAT-ML-PRICE-MODEL-V2).
Tuân thủ 4 nhóm kiểm thử bắt buộc:
1. Happy Path
2. Boundary & Edge Cases (Toàn quốc + Adaptive Room Type: Sleepbox/KTX, Nguyên căn)
3. State Mutation & Anti-Leakage
4. Persistence (Joblib Serialization)
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


# ==============================================================================
# NHÓM 1: HAPPY PATH
# ==============================================================================
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


def test_input_guard_nationwide_happy_path():
    """Kiểm tra InputGuard chấp nhận phòng hợp lệ ở TP.HCM, Hà Nội, Đà Nẵng, Cần Thơ, Đà Lạt."""
    df_train, _ = _make_sample_df(50)
    guard = InputGuard().fit(df_train)

    X_cities = pd.DataFrame({
        "area_m2": [25.0, 28.0, 30.0, 22.0, 35.0],
        "lat": [10.7769, 21.0285, 16.0544, 10.0452, 11.9404],  # HCM, HN, ĐN, CT, Đà Lạt
        "lng": [106.7009, 105.8542, 108.2022, 105.7469, 108.4583],
        "room_type_id": [1, 2, 2, 1, 3],
    })
    prices = np.array([3_500_000, 4_500_000, 4_200_000, 2_200_000, 7_500_000])

    res = guard.check(X_cities, prices)
    assert res["status"].tolist() == ["ok", "ok", "ok", "ok", "ok"]


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================
def test_input_guard_sleepbox_low_ppm_and_whole_house_high_price():
    """
    Kiểm tra thích ứng theo room_type_id:
    - SLEEPBOX (4) có diện tích phòng chung 100m2, giá 800k (ppm = 8,000 >= 5,000) -> 'ok'
    - ROOM (1) cùng diện tích 100m2, giá 800k (ppm = 8,000 < 12,000) -> 'odd'
    - WHOLE_HOUSE (5) giá 30tr, diện tích 150m2 -> 'ok'
    - ROOM (1) giá 30tr (> 15tr) -> 'oor'
    """
    guard = InputGuard()
    X_test = pd.DataFrame({
        "area_m2": [100.0, 100.0, 150.0, 30.0, 25.0],
        "lat": [10.7769, 10.7769, 21.0285, 21.0285, 1.3521],  # Dòng cuối ở Singapore (ngoài VN)
        "lng": [106.7009, 106.7009, 105.8542, 105.8542, 103.8198],
        "room_type_id": [4, 1, 5, 1, 1],
    })
    prices = np.array([800_000, 800_000, 30_000_000, 30_000_000, 3_500_000])

    statuses = guard.check(X_test, prices)["status"].tolist()
    assert statuses[0] == "ok"   # Sleepbox ở ghép hợp lệ (ppm = 8,000)
    assert statuses[1] == "odd"  # Phòng trọ thường ppm = 8,000 < 12,000 -> bất thường
    assert statuses[2] == "ok"   # Nhà nguyên căn 30tr hợp lệ
    assert statuses[3] == "oor"  # Phòng trọ thường 30tr -> vượt biên giá
    assert statuses[4] == "oor"  # Tọa độ ngoài lãnh thổ Việt Nam


# ==============================================================================
# NHÓM 3: STATE MUTATION & ANTI-DATA-LEAKAGE
# ==============================================================================
def test_make_base_features_immutability():
    """Đảm bảo make_base_features không mutate DataFrame gốc."""
    df, _ = _make_sample_df(5)
    orig_cols = list(df.columns)
    _ = make_base_features(df)
    assert list(df.columns) == orig_cols


def test_spatial_te_transform_train_prevents_self_leakage():
    """
    Kiểm tra transform_train loại bỏ chính bản ghi đang xét:
    Nếu dòng 0 có giá cực đại 1 tỷ VNĐ nhưng tất cả láng giềng có giá 3 triệu VNĐ,
    thì feature láng giềng của dòng 0 khi transform_train phải bằng đúng log1p(3_000_000).
    """
    X = pd.DataFrame({
        "lat": [10.770, 10.771, 10.772, 10.773, 10.774, 10.775],
        "lng": [106.650, 106.651, 106.652, 106.653, 106.654, 106.655],
        "area_m2": [20.0] * 6,
    })
    y = pd.Series([1_000_000_000.0] + [3_000_000.0] * 5)

    te = SpatialTE(ks=(5,)).fit(X, y)
    tr_feat = te.transform_train(X)

    expected_logy = np.log1p(3_000_000.0)
    assert np.isclose(tr_feat["nb5_logy_mean"].iloc[0], expected_logy, atol=1e-5)


# ==============================================================================
# NHÓM 4: PERSISTENCE TEST (JOBLIB SERIALIZATION)
# ==============================================================================
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


def test_price_evaluator_real_artifacts():
    """Kiểm tra PriceEvaluator nạp artifacts thực tế và chấm điểm cho nhiều tỉnh thành & loại phòng."""
    from crawler.model.ml.price_evaluator import PriceEvaluator

    evaluator = PriceEvaluator()
    assert evaluator.evaluate_batch([]).empty

    records = [
        {
            "listing_id": "hcm_room_1",
            "price_vnd": 3_200_000,
            "area_m2": 20.0,
            "lat": 10.772,
            "lng": 106.657,
            "room_type_id": 1,
            "aircon": True,
            "private_wc": True,
        },
        {
            "listing_id": "hn_sleepbox_1",
            "price_vnd": 1_500_000,
            "area_m2": 60.0,
            "lat": 21.037,
            "lng": 105.781,
            "room_type_id": 4,
            "aircon": True,
        },
        {
            "listing_id": "dn_studio_1",
            "price_vnd": 4_200_000,
            "area_m2": 28.0,
            "lat": 16.061,
            "lng": 108.220,
            "room_type_id": 2,
            "aircon": True,
            "private_wc": True,
            "kitchen": True,
        },
    ]

    df_res = evaluator.evaluate_batch(records)
    assert len(df_res) == 3
    assert df_res["guard_status"].tolist() == ["ok", "ok", "ok"]
    assert ((df_res["price_score"] >= 0.0) & (df_res["price_score"] <= 1.0)).all()
    assert (df_res["price_low"] <= df_res["price_mid"]).all()
    assert (df_res["price_mid"] <= df_res["price_high"]).all()
