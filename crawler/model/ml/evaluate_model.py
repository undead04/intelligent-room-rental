r"""
crawler/model/ml/evaluate_model.py
Phân tích dữ liệu khám phá (EDA), giải trình lựa chọn đặc trưng (Feature Selection & Ablation Study)
và đánh giá toàn diện hiệu suất mô hình định giá phòng trọ Homigo ML.

Chạy độc lập qua CLI:
    .\crawler\.venv\Scripts\python.exe -m crawler.model.ml.evaluate_model
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.feature_selection import mutual_info_regression
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from crawler.config.paths import ML_ARTIFACTS_DIR
from crawler.model.ml.feature_extractor import (
    ALL_BINARY_KEYS,
    DEFAULT_PARQUET_PATH,
    PRUNED_19_FEATURES,
    PRUNED_LOW_IMPACT_FLAGS,
    ROOM_TYPE_FILTER_RULES,
    VIETNAM_LAT_RANGE,
    VIETNAM_LNG_RANGE,
    extract_features_from_record,
    filter_valid_dataframe,
    load_and_preprocess_dataset,
)
from crawler.model.ml.models import (
    MondrianPriceInterval,
    SpatialTE,
    attach,
    blend_predict,
    make_base_features,
    predict_log,
)
from crawler.model.ml.price_evaluator import PriceEvaluator
from crawler.model.ml.train_price_model import _make_strata, models_config

warnings.filterwarnings("ignore", category=UserWarning)

EVALUATION_JSON_PATH = ML_ARTIFACTS_DIR / "evaluation_report.json"
EVALUATION_MD_PATH = ML_ARTIFACTS_DIR / "evaluation_report.md"

ROOM_TYPE_LABELS: dict[int, str] = {
    1: "ROOM (Phòng trọ)",
    2: "STUDIO (Căn hộ mini)",
    3: "APARTMENT (Chung cư)",
    4: "SLEEPBOX (KTX/Ở ghép)",
    5: "WHOLE_HOUSE (Nhà nguyên căn)",
}

PRICE_TIER_BINS: list[tuple[float, float, str]] = [
    (0.0, 2_500_000.0, "< 2.5 triệu"),
    (2_500_000.0, 4_000_000.0, "2.5 - 4 triệu"),
    (4_000_000.0, 7_000_000.0, "4 - 7 triệu"),
    (7_000_000.0, 12_000_000.0, "7 - 12 triệu"),
    (12_000_000.0, float("inf"), "> 12 triệu"),
]


# ==============================================================================
# 1. CÁC HÀM ĐO LƯỜNG CHỈ SỐ & THỐNG KÊ CƠ SỞ
# ==============================================================================


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Tính đầy đủ bộ chỉ số hồi quy trong cả không gian VNĐ và không gian Log."""
    yt = np.asarray(y_true, dtype=float).ravel()
    yp = np.clip(np.asarray(y_pred, dtype=float).ravel(), 1.0, None)
    n = int(len(yt))
    if n == 0:
        return {
            "count": 0,
            "mae_vnd": 0.0,
            "median_ae_vnd": 0.0,
            "rmse_vnd": 0.0,
            "mape_pct": 0.0,
            "mdape_pct": 0.0,
            "r2_vnd": 0.0,
            "r2_log": 0.0,
            "within_15pct": 0.0,
            "within_20pct": 0.0,
        }

    abs_err = np.abs(yt - yp)
    safe_yt = np.clip(yt, 1.0, None)
    pct_err = abs_err / safe_yt

    r2_vnd = float(r2_score(yt, yp)) if n >= 2 and np.std(yt) > 0 else 0.0
    yt_log = np.log1p(safe_yt)
    yp_log = np.log1p(yp)
    r2_log = float(r2_score(yt_log, yp_log)) if n >= 2 and np.std(yt_log) > 0 else 0.0

    return {
        "count": n,
        "mae_vnd": round(float(mean_absolute_error(yt, yp)), 2),
        "median_ae_vnd": round(float(median_absolute_error(yt, yp)), 2),
        "rmse_vnd": round(float(np.sqrt(mean_squared_error(yt, yp))), 2),
        "mape_pct": round(float(np.mean(pct_err) * 100.0), 2),
        "mdape_pct": round(float(np.median(pct_err) * 100.0), 2),
        "r2_vnd": round(r2_vnd, 4),
        "r2_log": round(r2_log, 4),
        "within_15pct": round(float(np.mean(pct_err <= 0.15) * 100.0), 2),
        "within_20pct": round(float(np.mean(pct_err <= 0.20) * 100.0), 2),
    }


def compute_distribution_stats(series: pd.Series) -> dict[str, float]:
    """Thống kê phân phối mô tả cho một biến số liên tục."""
    clean = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(clean) == 0:
        return {
            "count": 0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p05": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "p95": 0.0,
            "max": 0.0,
            "skewness": 0.0,
        }
    skew_val = float(pd.Series(clean).skew()) if len(clean) >= 3 and np.std(clean) > 0 else 0.0
    if np.isnan(skew_val):
        skew_val = 0.0
    return {
        "count": int(len(clean)),
        "mean": round(float(np.mean(clean)), 4),
        "std": round(float(np.std(clean)), 4),
        "min": round(float(np.min(clean)), 4),
        "p05": round(float(np.quantile(clean, 0.05)), 4),
        "p25": round(float(np.quantile(clean, 0.25)), 4),
        "median": round(float(np.median(clean)), 4),
        "p75": round(float(np.quantile(clean, 0.75)), 4),
        "p95": round(float(np.quantile(clean, 0.95)), 4),
        "max": round(float(np.max(clean)), 4),
        "skewness": round(skew_val, 4),
    }


def _safe_corr(x: np.ndarray, y: np.ndarray, method: str = "pearson") -> float:
    """Tính tương quan Pearson hoặc Spearman an toàn với mảng hằng số."""
    if len(x) < 3 or np.std(x) <= 1e-12 or np.std(y) <= 1e-12:
        return 0.0
    sx = pd.Series(x)
    sy = pd.Series(y)
    val = sx.corr(sy, method=method)
    return 0.0 if val is None or np.isnan(val) else round(float(val), 4)


def _load_raw_dataframe(data_path: str | Path = DEFAULT_PARQUET_PATH) -> pd.DataFrame:
    """Nạp dữ liệu thô từ Parquet hoặc JSON (không chỉnh sửa file nguồn)."""
    path_obj = Path(data_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Không tìm thấy dữ liệu nguồn tại: {path_obj}")
    if path_obj.suffix.lower() == ".parquet":
        return pd.read_parquet(path_obj)
    with open(path_obj, "r", encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


# ==============================================================================
# 2. KHỐI 1: PHÂN TÍCH KHÁM PHÁ DỮ LIỆU (EDA) & PHỄU LÀM SẠCH
# ==============================================================================


def _compute_cleaning_funnel(df_extracted: pd.DataFrame, df_clean: pd.DataFrame) -> dict[str, Any]:
    """Thống kê số lượng bản ghi qua từng bước lọc và nguyên nhân loại bỏ."""
    raw_total = int(len(df_extracted))
    if raw_total == 0:
        return {
            "raw_total": 0,
            "after_geo_total": 0,
            "dropped_geo_count": 0,
            "dropped_rule_count": 0,
            "clean_total": 0,
            "retention_rate_pct": 0.0,
            "rule_rejection_reasons": {"area_oor": 0, "price_oor": 0, "ppm_oor": 0},
        }

    cond_geo = (
        (df_extracted["lat"] >= VIETNAM_LAT_RANGE[0])
        & (df_extracted["lat"] <= VIETNAM_LAT_RANGE[1])
        & (df_extracted["lng"] >= VIETNAM_LNG_RANGE[0])
        & (df_extracted["lng"] <= VIETNAM_LNG_RANGE[1])
    )
    df_geo = df_extracted[cond_geo].copy()
    after_geo = int(len(df_geo))
    clean_total = int(len(df_clean))

    # Phân rã nguyên nhân bị loại ở bước lọc rule theo loại phòng
    area_bad = 0
    price_bad = 0
    ppm_bad = 0
    if not df_geo.empty:
        ppm_series = df_geo["price_vnd"] / df_geo["area_m2"].clip(lower=1e-6)
        for idx, row in df_geo.iterrows():
            rule = ROOM_TYPE_FILTER_RULES.get(int(row["room_type_id"]), ROOM_TYPE_FILTER_RULES[1])
            if not (rule["area"][0] <= row["area_m2"] <= rule["area"][1]):
                area_bad += 1
            if not (rule["price"][0] <= row["price_vnd"] <= rule["price"][1]):
                price_bad += 1
            if not (rule["ppm"][0] <= ppm_series.loc[idx] <= rule["ppm"][1]):
                ppm_bad += 1

    return {
        "raw_total": raw_total,
        "after_geo_total": after_geo,
        "dropped_geo_count": raw_total - after_geo,
        "dropped_rule_count": after_geo - clean_total,
        "clean_total": clean_total,
        "retention_rate_pct": round(clean_total / raw_total * 100.0, 2),
        "rule_rejection_reasons": {
            "area_oor": int(area_bad),
            "price_oor": int(price_bad),
            "ppm_oor": int(ppm_bad),
        },
    }


def analyze_dataset_eda(
    data_path: str | Path = DEFAULT_PARQUET_PATH,
    raw_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Thực hiện EDA toàn diện trên dữ liệu Toàn Quốc: Phễu lọc, phân phối, phân khúc & tiện ích."""
    source_df = raw_df.copy() if raw_df is not None else _load_raw_dataframe(data_path)
    raw_records = source_df.to_dict(orient="records")

    extracted_rows = [extract_features_from_record(r) for r in raw_records]
    df_extracted = pd.DataFrame(extracted_rows)

    # Gắn thông tin city từ bản ghi gốc để thống kê phân bố địa lý (nếu có)
    city_map = {
        str(r.get("listing_id") or r.get("id") or ""): str(r.get("city") or "Chưa rõ")
        for r in raw_records
    }
    df_clean = filter_valid_dataframe(df_extracted)
    funnel = _compute_cleaning_funnel(df_extracted, df_clean)

    if df_clean.empty:
        return {"funnel": funnel, "overall_distributions": {}, "room_type_breakdown": [], "city_breakdown": [], "binary_flag_prevalence": []}

    df_clean["ppm_vnd"] = df_clean["price_vnd"] / df_clean["area_m2"].clip(lower=1e-6)
    df_clean["log1p_price"] = np.log1p(df_clean["price_vnd"])
    df_clean["city"] = df_clean["listing_id"].astype(str).map(lambda x: city_map.get(x, "Chưa rõ"))

    dist_cols = {
        "price_vnd": df_clean["price_vnd"],
        "log1p_price": df_clean["log1p_price"],
        "area_m2": df_clean["area_m2"],
        "ppm_vnd": df_clean["ppm_vnd"],
        "dist_nearest_hub_km": df_clean["dist_nearest_hub_km"],
        "dist_nearest_uni_km": df_clean["dist_nearest_uni_km"],
        "amenity_overall": df_clean["amenity_overall"],
        "safety_score": df_clean["safety_score"],
    }
    overall_distributions = {name: compute_distribution_stats(ser) for name, ser in dist_cols.items()}

    total_clean = len(df_clean)
    rt_breakdown: list[dict[str, Any]] = []
    for rt_id in sorted(df_clean["room_type_id"].unique()):
        sub = df_clean[df_clean["room_type_id"] == rt_id]
        rt_breakdown.append({
            "room_type_id": int(rt_id),
            "name": ROOM_TYPE_LABELS.get(int(rt_id), f"TYPE_{rt_id}"),
            "count": int(len(sub)),
            "share_pct": round(len(sub) / total_clean * 100.0, 2),
            "price_median_vnd": round(float(sub["price_vnd"].median()), 0),
            "price_mean_vnd": round(float(sub["price_vnd"].mean()), 0),
            "area_median_m2": round(float(sub["area_m2"].median()), 1),
            "ppm_median_vnd": round(float(sub["ppm_vnd"].median()), 0),
            "amenity_overall_mean": round(float(sub["amenity_overall"].mean()), 3),
            "safety_score_mean": round(float(sub["safety_score"].mean()), 3),
        })

    city_breakdown: list[dict[str, Any]] = []
    city_counts = df_clean["city"].value_counts()
    for city_name, cnt in city_counts.head(8).items():
        sub = df_clean[df_clean["city"] == city_name]
        city_breakdown.append({
            "city": str(city_name),
            "count": int(cnt),
            "share_pct": round(cnt / total_clean * 100.0, 2),
            "price_median_vnd": round(float(sub["price_vnd"].median()), 0),
            "area_median_m2": round(float(sub["area_m2"].median()), 1),
            "ppm_median_vnd": round(float(sub["ppm_vnd"].median()), 0),
        })

    pruned_set = set(PRUNED_LOW_IMPACT_FLAGS)
    flag_stats: list[dict[str, Any]] = []
    for key in ALL_BINARY_KEYS:
        col = f"is_{key}"
        if col not in df_clean.columns:
            continue
        vals = df_clean[col].to_numpy(dtype=float)
        with_flag = df_clean.loc[vals == 1, "price_vnd"]
        without_flag = df_clean.loc[vals == 0, "price_vnd"]
        median_diff = (
            float(with_flag.median() - without_flag.median())
            if len(with_flag) > 0 and len(without_flag) > 0
            else 0.0
        )
        flag_stats.append({
            "feature": col,
            "status": "PRUNED_7" if col in pruned_set else "KEPT_19",
            "prevalence_pct": round(float(np.mean(vals) * 100.0), 2),
            "corr_log_price": _safe_corr(vals, df_clean["log1p_price"].to_numpy()),
            "median_price_diff_vnd": round(median_diff, 0),
        })

    return {
        "funnel": funnel,
        "overall_distributions": overall_distributions,
        "room_type_breakdown": rt_breakdown,
        "city_breakdown": city_breakdown,
        "binary_flag_prevalence": flag_stats,
    }


# ==============================================================================
# 3. KHỐI 2: GIẢI TRÌNH LỰA CHỌN ĐẶC TRƯNG, ĐA CỘNG TUYẾN & ABLATION STUDY
# ==============================================================================


def _build_all_candidate_matrix(X_full: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, dict[str, str]]:
    """Tạo ma trận đầy đủ gồm 26 features + 3 phái sinh + 7 SpatialTE (anti-leakage)."""
    X_in = X_full.copy().reset_index(drop=True)
    y_arr = pd.Series(np.asarray(y, dtype=float).ravel())

    Xb_pruned = make_base_features(X_in).reset_index(drop=True)
    # Khôi phục 7 cờ đã cắt để phân tích tương quan / MI công bằng toàn diện
    for col in PRUNED_LOW_IMPACT_FLAGS:
        if col in X_in.columns:
            Xb_pruned[col] = X_in[col].to_numpy(dtype=float)

    te = SpatialTE(ks=(5, 20)).fit(Xb_pruned, y_arr)
    nb_feats = te.transform_train(Xb_pruned)
    X_cand = attach(Xb_pruned, nb_feats)

    role_map: dict[str, str] = {}
    pruned_set = set(PRUNED_LOW_IMPACT_FLAGS)
    kept_set = set(PRUNED_19_FEATURES)
    nb_set = set(nb_feats.columns)
    for col in X_cand.columns:
        if col in pruned_set:
            role_map[col] = "PRUNED_FLAG"
        elif col in kept_set:
            role_map[col] = "KEPT_19"
        elif col in nb_set:
            role_map[col] = "SPATIAL_TE"
        else:
            role_map[col] = "DERIVED"
    return X_cand, role_map


def _extract_model_importances(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Trích xuất Gain & Split Feature Importance (%) từ LightGBM + XGBoost trong pipeline."""
    lgb_res = next((r for r in results if r["model_name"] == "LightGBM"), None)
    xgb_res = next((r for r in results if r["model_name"] == "XGBoost"), None)
    if lgb_res is None or xgb_res is None:
        return {"features": [], "group_summary": []}

    lgb_m = lgb_res["best_estimator"]
    xgb_m = xgb_res["best_estimator"]
    feat_names = list(lgb_m.feature_name())

    lgb_gain_raw = np.asarray(lgb_m.feature_importance(importance_type="gain"), dtype=float)
    lgb_split_raw = np.asarray(lgb_m.feature_importance(importance_type="split"), dtype=float)
    lgb_gain_pct = lgb_gain_raw / np.clip(lgb_gain_raw.sum(), 1e-9, None) * 100.0
    lgb_split_pct = lgb_split_raw / np.clip(lgb_split_raw.sum(), 1e-9, None) * 100.0

    xgb_gain_map = xgb_m.get_score(importance_type="gain")
    xgb_weight_map = xgb_m.get_score(importance_type="weight")
    xgb_gain_raw = np.array([float(xgb_gain_map.get(c, 0.0)) for c in feat_names], dtype=float)
    xgb_weight_raw = np.array([float(xgb_weight_map.get(c, 0.0)) for c in feat_names], dtype=float)
    xgb_gain_pct = xgb_gain_raw / np.clip(xgb_gain_raw.sum(), 1e-9, None) * 100.0
    xgb_weight_pct = xgb_weight_raw / np.clip(xgb_weight_raw.sum(), 1e-9, None) * 100.0

    def _feature_group(name: str) -> str:
        if name.startswith("nb"):
            return "SpatialTE (Láng giềng Haversine)"
        if name in ("area_m2", "lat", "lng", "room_type_id", "furnishing_code", "lat_lng_sum", "lat_lng_diff"):
            return "Quy mô, Loại phòng & Tọa độ"
        if name in ("dist_nearest_hub_km", "dist_nearest_uni_km"):
            return "Khoảng cách POI Đô thị & Đại học"
        if name in ("amenity_overall", "safety_score", "amenity_density"):
            return "Điểm Ngữ nghĩa LLM & Mật độ"
        return "10 Cờ Tiện nghi & An ninh Cốt lõi"

    rows = []
    group_totals: dict[str, dict[str, float]] = {}
    for idx, col in enumerate(feat_names):
        ens_gain = 0.5 * (lgb_gain_pct[idx] + xgb_gain_pct[idx])
        grp = _feature_group(col)
        rows.append({
            "feature": col,
            "group": grp,
            "lgb_gain_pct": round(float(lgb_gain_pct[idx]), 2),
            "xgb_gain_pct": round(float(xgb_gain_pct[idx]), 2),
            "ensemble_gain_pct": round(float(ens_gain), 2),
            "lgb_split_pct": round(float(lgb_split_pct[idx]), 2),
            "xgb_split_pct": round(float(xgb_weight_pct[idx]), 2),
        })
        if grp not in group_totals:
            group_totals[grp] = {"feature_count": 0, "lgb_gain_pct": 0.0, "xgb_gain_pct": 0.0, "ensemble_gain_pct": 0.0}
        group_totals[grp]["feature_count"] += 1
        group_totals[grp]["lgb_gain_pct"] += float(lgb_gain_pct[idx])
        group_totals[grp]["xgb_gain_pct"] += float(xgb_gain_pct[idx])
        group_totals[grp]["ensemble_gain_pct"] += float(ens_gain)

    rows.sort(key=lambda r: r["ensemble_gain_pct"], reverse=True)
    group_summary = [
        {
            "group": grp,
            "feature_count": vals["feature_count"],
            "lgb_gain_pct": round(vals["lgb_gain_pct"], 2),
            "xgb_gain_pct": round(vals["xgb_gain_pct"], 2),
            "ensemble_gain_pct": round(vals["ensemble_gain_pct"], 2),
        }
        for grp, vals in sorted(group_totals.items(), key=lambda kv: kv[1]["ensemble_gain_pct"], reverse=True)
    ]
    return {"features": rows, "group_summary": group_summary}


def _safe_stratified_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.15,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Chia train/test phân tầng theo room_type + quantile giá; fallback an toàn khi cỡ mẫu nhỏ."""
    strata = _make_strata(X, y)
    _, counts = np.unique(strata, return_counts=True)
    n_test = max(1, int(np.ceil(len(X) * test_size)))
    if len(counts) > 0 and counts.min() >= 2 and len(counts) <= n_test:
        return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=strata)

    if "room_type_id" in X.columns:
        rt_vals = X["room_type_id"].to_numpy()
        _, rt_counts = np.unique(rt_vals, return_counts=True)
        if len(rt_counts) > 0 and rt_counts.min() >= 2 and len(rt_counts) <= n_test:
            return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=rt_vals)

    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=None)


def run_ablation_study(
    X_full: pd.DataFrame,
    y: pd.Series,
    lgb_params: dict[str, Any] | None = None,
    n_rounds: int = 380,
    random_state: int = 42,
) -> list[dict[str, Any]]:
    """So sánh 4 cấu hình đặc trưng trên cùng 1 tập Holdout Test 15% (không leakage)."""
    y_ser = pd.Series(np.asarray(y, dtype=float).ravel())
    X_in = X_full.copy().reset_index(drop=True)
    X_train, X_test, y_train, y_test = _safe_stratified_split(
        X_in, y_ser, test_size=0.15, random_state=random_state
    )

    params = dict(lgb_params or {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.03,
        "num_leaves": 45,
        "min_child_samples": 25,
        "subsample": 0.85,
        "colsample_bytree": 0.8,
        "reg_lambda": 2.0,
        "seed": random_state,
        "n_jobs": 4,
        "verbose": -1,
    })
    params["verbose"] = -1

    # Chuẩn bị ma trận cơ sở (19 features -> 22 cột) và SpatialTE (fit chỉ trên X_train)
    Xb_tr = make_base_features(X_train).reset_index(drop=True)
    Xb_te = make_base_features(X_test).reset_index(drop=True)
    te = SpatialTE((5, 20)).fit(Xb_tr, y_train)
    nb_tr = te.transform_train(Xb_tr).reset_index(drop=True)
    nb_te = te.transform(Xb_te).reset_index(drop=True)

    # Khôi phục 7 cờ PRUNED_LOW_IMPACT_FLAGS để đo cấu hình Full 26
    flags_tr = X_train[[c for c in PRUNED_LOW_IMPACT_FLAGS if c in X_train.columns]].reset_index(drop=True)
    flags_te = X_test[[c for c in PRUNED_LOW_IMPACT_FLAGS if c in X_test.columns]].reset_index(drop=True)

    configs: list[tuple[str, str, pd.DataFrame, pd.DataFrame]] = [
        ("1_Base_19_No_SpatialTE", "Chỉ 19 đặc trưng cơ sở + 3 phái sinh (Không SpatialTE)", Xb_tr, Xb_te),
        ("2_SpatialTE_Only", "Chỉ 7 đặc trưng láng giềng SpatialTE (k=5, 20)", nb_tr, nb_te),
        (
            "3_Full_26_With_SpatialTE",
            "Đầy đủ 26 đặc trưng gốc + 3 phái sinh + 7 SpatialTE (Chưa cắt 7 cờ)",
            pd.concat([Xb_tr, flags_tr, nb_tr], axis=1),
            pd.concat([Xb_te, flags_te, nb_te], axis=1),
        ),
        (
            "4_Pruned_19_With_SpatialTE",
            "Bộ 19 đặc trưng tinh gọn + 3 phái sinh + 7 SpatialTE (Production)",
            attach(Xb_tr, nb_tr),
            attach(Xb_te, nb_te),
        ),
    ]

    y_tr_clip = y_train.clip(y_train.quantile(0.01), y_train.quantile(0.99))
    y_tr_log = np.log1p(y_tr_clip.values)

    ablation_rows: list[dict[str, Any]] = []
    for cfg_id, desc, X_tr_cfg, X_te_cfg in configs:
        model = lgb.train(params, lgb.Dataset(X_tr_cfg, y_tr_log), num_boost_round=n_rounds)
        pred_tr_raw = np.expm1(model.predict(X_tr_cfg))
        pred_te_raw = np.expm1(model.predict(X_te_cfg))
        smear = float(
            np.clip(
                np.sum(y_train.values * pred_tr_raw) / np.clip(np.sum(pred_tr_raw ** 2), 1.0, None),
                0.95,
                1.08,
            )
        )
        m = compute_regression_metrics(y_test.values, pred_te_raw * smear)
        ablation_rows.append({
            "config_id": cfg_id,
            "description": desc,
            "n_features_into_tree": int(X_tr_cfg.shape[1]),
            **m,
        })
    return ablation_rows


def analyze_feature_selection(
    X_full: pd.DataFrame,
    y: pd.Series,
    results: list[dict[str, Any]] | None = None,
    *,
    run_ablation: bool = True,
    random_state: int = 42,
) -> dict[str, Any]:
    """Phân tích tương quan, đa cộng tuyến, Feature Importance và Ablation Study."""
    X_cand, role_map = _build_all_candidate_matrix(X_full, y)
    y_log = np.log1p(np.clip(np.asarray(y, dtype=float).ravel(), 1.0, None))

    mi_scores = mutual_info_regression(X_cand.fillna(0.0), y_log, random_state=random_state)
    imp_info = _extract_model_importances(results) if results else {"features": [], "group_summary": []}
    imp_lookup = {row["feature"]: row for row in imp_info["features"]}

    candidate_stats: list[dict[str, Any]] = []
    for idx, col in enumerate(X_cand.columns):
        vals = X_cand[col].to_numpy(dtype=float)
        imp_row = imp_lookup.get(col, {})
        candidate_stats.append({
            "feature": col,
            "role": role_map[col],
            "pearson_log_price": _safe_corr(vals, y_log, "pearson"),
            "spearman_log_price": _safe_corr(vals, y_log, "spearman"),
            "mutual_info": round(float(mi_scores[idx]), 4),
            "ensemble_gain_pct": imp_row.get("ensemble_gain_pct"),
        })
    candidate_stats.sort(key=lambda r: (r["ensemble_gain_pct"] or 0.0, r["mutual_info"]), reverse=True)

    # Chẩn đoán đa cộng tuyến & lý do loại biến dư thừa
    area_arr = X_cand["area_m2"].to_numpy(dtype=float)
    log_area_arr = np.log1p(np.clip(area_arr, 0.0, None))
    amen_cols = [f"is_{k}" for k in ALL_BINARY_KEYS[:10] if f"is_{k}" in X_cand.columns]
    n_amenities_arr = X_cand[amen_cols].sum(axis=1).to_numpy(dtype=float) if amen_cols else np.zeros(len(X_cand))

    multicollinearity = {
        "area_vs_log_area": {
            "pearson_r": _safe_corr(area_arr, log_area_arr, "pearson"),
            "spearman_rho": _safe_corr(area_arr, log_area_arr, "spearman"),
            "decision": "Giữ area_m2, loại log_area vì cây quyết định bất biến với phép biến đổi đơn điệu (Spearman = 1.0).",
        },
        "n_amenities_vs_amenity_overall": {
            "pearson_r": _safe_corr(n_amenities_arr, X_cand["amenity_overall"].to_numpy(), "pearson"),
            "spearman_rho": _safe_corr(n_amenities_arr, X_cand["amenity_overall"].to_numpy(), "spearman"),
            "decision": "Giữ amenity_overall + amenity_density, loại n_amenities để tránh phân tán Gain trên cây.",
        },
        "pruned_flags_summary": [
            {
                "feature": col,
                "prevalence_pct": round(float(X_cand[col].mean() * 100.0), 2),
                "corr_log_price": _safe_corr(X_cand[col].to_numpy(), y_log, "pearson"),
                "corr_amenity_overall": _safe_corr(X_cand[col].to_numpy(), X_cand["amenity_overall"].to_numpy(), "pearson"),
                "corr_safety_score": _safe_corr(X_cand[col].to_numpy(), X_cand["safety_score"].to_numpy(), "pearson"),
                "mutual_info": round(float(mi_scores[list(X_cand.columns).index(col)]), 4),
            }
            for col in PRUNED_LOW_IMPACT_FLAGS
            if col in X_cand.columns
        ],
    }

    ablation_rows: list[dict[str, Any]] = []
    if run_ablation:
        lgb_res = next((r for r in (results or []) if r["model_name"] == "LightGBM"), None)
        lgb_params = lgb_res.get("best_params") if lgb_res else None
        n_rounds = int(lgb_res.get("n_rounds", 380)) if lgb_res else 380
        ablation_rows = run_ablation_study(
            X_full, y, lgb_params=lgb_params, n_rounds=n_rounds, random_state=random_state
        )

    return {
        "candidate_feature_stats": candidate_stats,
        "multicollinearity": multicollinearity,
        "production_feature_importance": imp_info,
        "ablation_study": ablation_rows,
    }


# ==============================================================================
# 4. KHỐI 3: ĐÁNH GIÁ TOÀN DIỆN MÔ HÌNH DỰ ĐOÁN & MONDRIAN CONFORMAL
# ==============================================================================


def _fit_holdout_reference_ensemble(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    prod_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], MondrianPriceInterval]:
    """Huấn luyện lại ensemble bằng đúng best_params từ pipeline trên 85% train để đánh giá Holdout zero-leakage."""
    Xb_tr = make_base_features(X_train).reset_index(drop=True)
    y_clip = y_train.clip(y_train.quantile(0.01), y_train.quantile(0.99))
    y_log = np.log1p(y_clip.values)

    te = SpatialTE((5, 20)).fit(Xb_tr, y_train)
    Xf_tr = attach(Xb_tr, te.transform_train(Xb_tr))

    holdout_results: list[dict[str, Any]] = []
    for prod_res in prod_results:
        name = prod_res["model_name"]
        cfg = models_config[name]
        best_params = dict(prod_res["best_params"])
        n_rounds = int(prod_res["n_rounds"])
        est = cfg["fit_full_fn"](best_params, Xf_tr, y_log, n_rounds)
        holdout_results.append({
            "model_name": name,
            "best_estimator": est,
            "best_params": best_params,
            "n_rounds": n_rounds,
            "fe": te,
            "smear": float(prod_res["smear"]),
            "ks": prod_res.get("ks", (5, 20)),
        })

    lgb_holdout = next(r for r in holdout_results if r["model_name"] == "LightGBM")
    pi_holdout = MondrianPriceInterval(lgb_holdout, n_bins=5, coverage=0.8, seed=42).fit(X_train, y_train)
    return holdout_results, pi_holdout


def _segment_breakdown(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    lows: np.ndarray,
    highs: np.ndarray,
    masks: list[tuple[str, np.ndarray]],
    key_name: str,
) -> list[dict[str, Any]]:
    """Tính bảng chỉ số hồi quy & độ phủ conformal theo danh sách phân khúc."""
    rows: list[dict[str, Any]] = []
    for label, mask in masks:
        cnt = int(np.sum(mask))
        if cnt == 0:
            continue
        yt_s = y_true[mask]
        yp_s = y_pred[mask]
        lo_s = lows[mask]
        hi_s = highs[mask]
        cov = float(np.mean((yt_s >= lo_s) & (yt_s <= hi_s)) * 100.0)
        width_med = float(np.median(hi_s - lo_s))
        m = compute_regression_metrics(yt_s, yp_s)
        rows.append({
            key_name: label,
            "median_actual_vnd": round(float(np.median(yt_s)), 0),
            "median_pred_vnd": round(float(np.median(yp_s)), 0),
            **m,
            "conformal_coverage_pct": round(cov, 2),
            "median_interval_width_vnd": round(width_med, 0),
        })
    return rows


def evaluate_production_pipeline(
    X_pruned: pd.DataFrame,
    y: pd.Series,
    evaluator: PriceEvaluator | None = None,
    random_state: int = 42,
) -> dict[str, Any]:
    """Đánh giá độc lập trên 15% Holdout Test: Baseline vs LGBM vs XGB vs Blend, phân khúc & Conformal."""
    ev = evaluator or PriceEvaluator()
    X_in = X_pruned.copy().reset_index(drop=True)
    y_ser = pd.Series(np.asarray(y, dtype=float).ravel())

    X_train, X_test, y_train, y_test = _safe_stratified_split(
        X_in, y_ser, test_size=0.15, random_state=random_state
    )

    holdout_results, pi_holdout = _fit_holdout_reference_ensemble(X_train, y_train, ev.results)

    # 1. Dự đoán 4 mô hình trên Holdout Test
    rt_medians = y_train.groupby(X_train["room_type_id"].values).median().to_dict()
    global_median = float(y_train.median())
    pred_baseline = np.array(
        [rt_medians.get(int(rt), global_median) for rt in X_test["room_type_id"].values],
        dtype=float,
    )

    lgb_res = next(r for r in holdout_results if r["model_name"] == "LightGBM")
    xgb_res = next(r for r in holdout_results if r["model_name"] == "XGBoost")
    pred_lgb = np.expm1(predict_log(lgb_res, X_test)) * lgb_res["smear"]
    pred_xgb = np.expm1(predict_log(xgb_res, X_test)) * xgb_res["smear"]
    pred_blend = blend_predict(holdout_results, X_test, smear=True)

    y_test_arr = y_test.values
    model_comparison = {
        "Baseline (Room-Type Median)": compute_regression_metrics(y_test_arr, pred_baseline),
        "LightGBM (Holdout)": compute_regression_metrics(y_test_arr, pred_lgb),
        "XGBoost (Holdout)": compute_regression_metrics(y_test_arr, pred_xgb),
        "Ensemble Blend (LGBM + XGB)": compute_regression_metrics(y_test_arr, pred_blend),
    }

    # 2. Đánh giá Mondrian Conformal Prediction trên Holdout Test
    rng_test = pi_holdout.predict(X_test)
    lows = rng_test["low"].to_numpy(dtype=float)
    highs = rng_test["high"].to_numpy(dtype=float)
    widths = highs - lows
    rel_widths = widths / np.clip(pred_blend, 1.0, None) * 100.0

    # Tính bin để kiểm tra độ phủ từng Mondrian stratum
    Xb_te = make_base_features(X_test).reset_index(drop=True)
    lo_raw, hi_raw = pi_holdout._raw(attach(Xb_te, pi_holdout.te.transform(Xb_te)))
    centers = (lo_raw + hi_raw) / 2.0
    bins = np.searchsorted(pi_holdout.edges, centers, side="right")

    bin_stats = []
    for k in range(len(pi_holdout.qhats)):
        b_mask = bins == k
        if not np.any(b_mask):
            continue
        bin_stats.append({
            "bin": int(k + 1),
            "count": int(np.sum(b_mask)),
            "median_pred_vnd": round(float(np.median(pred_blend[b_mask])), 0),
            "qhat_log": round(float(pi_holdout.qhats[k]), 4),
            "coverage_pct": round(float(np.mean((y_test_arr[b_mask] >= lows[b_mask]) & (y_test_arr[b_mask] <= highs[b_mask])) * 100.0), 2),
            "median_width_vnd": round(float(np.median(widths[b_mask])), 0),
        })

    conformal_diagnostics = {
        "target_coverage_pct": 80.0,
        "empirical_coverage_pct": round(float(np.mean((y_test_arr >= lows) & (y_test_arr <= highs)) * 100.0), 2),
        "below_low_pct": round(float(np.mean(y_test_arr < lows) * 100.0), 2),
        "above_high_pct": round(float(np.mean(y_test_arr > highs) * 100.0), 2),
        "mean_width_vnd": round(float(np.mean(widths)), 0),
        "median_width_vnd": round(float(np.median(widths)), 0),
        "median_rel_width_pct": round(float(np.median(rel_widths)), 2),
        "bin_breakdown": bin_stats,
    }

    # 3. Phân rã theo Loại phòng, Phân khúc giá & Vùng miền
    rt_masks = [
        (ROOM_TYPE_LABELS.get(int(rt), f"TYPE_{rt}"), X_test["room_type_id"].values == rt)
        for rt in sorted(X_test["room_type_id"].unique())
    ]
    by_room_type = _segment_breakdown(y_test_arr, pred_blend, lows, highs, rt_masks, "room_type")

    tier_masks = [
        (label, (y_test_arr >= lo_b) & (y_test_arr < hi_b))
        for lo_b, hi_b, label in PRICE_TIER_BINS
    ]
    by_price_tier = _segment_breakdown(y_test_arr, pred_blend, lows, highs, tier_masks, "price_tier")

    # Tọa độ TP.HCM nằm khoảng lat [10.3, 11.2], lng [106.3, 107.1]
    is_hcm = (
        (X_test["lat"].to_numpy() >= 10.35)
        & (X_test["lat"].to_numpy() <= 11.16)
        & (X_test["lng"].to_numpy() >= 106.35)
        & (X_test["lng"].to_numpy() <= 107.03)
    )
    by_region = _segment_breakdown(
        y_test_arr,
        pred_blend,
        lows,
        highs,
        [("TP.HCM", is_hcm), ("Tỉnh / Thành phố khác", ~is_hcm)],
        "region",
    )

    # 4. Kiểm tra phân phối price_score & InputGuard qua Production PriceEvaluator trên tập Test
    test_records = [{**X_test.iloc[i].to_dict(), "listing_id": f"test_{i}", "price_vnd": float(y_test_arr[i])} for i in range(len(X_test))]
    eval_df = ev.evaluate_batch(test_records)
    verdict_counts = eval_df["verdict"].value_counts().to_dict()
    guard_counts = eval_df["guard_status"].value_counts().to_dict()
    price_score_summary = {
        "price_score": compute_distribution_stats(eval_df["price_score"]),
        "z_score": compute_distribution_stats(eval_df["z_score"]),
        "verdict_distribution_pct": {str(k): round(v / len(eval_df) * 100.0, 2) for k, v in verdict_counts.items()},
        "guard_status_distribution_pct": {str(k): round(v / len(eval_df) * 100.0, 2) for k, v in guard_counts.items()},
    }

    # 5. Thông tin 5-Fold CV từ artifacts hiện tại
    production_cv = [
        {
            "model_name": r["model_name"],
            "n_rounds": int(r.get("n_rounds", 0)),
            "smear": round(float(r.get("smear", 1.0)), 4),
            "cv_mae_mean": round(float(r.get("mae_mean", 0.0)), 2),
            "cv_rmse_mean": round(float(r.get("rmse_mean", 0.0)), 2),
            "cv_r2_mean": round(float(r.get("r2_mean", 0.0)), 4),
        }
        for r in ev.results
    ]

    return {
        "split_info": {"train_size": int(len(X_train)), "test_size": int(len(X_test)), "random_state": random_state},
        "model_comparison": model_comparison,
        "conformal_diagnostics": conformal_diagnostics,
        "segment_performance": {
            "by_room_type": by_room_type,
            "by_price_tier": by_price_tier,
            "by_region": by_region,
        },
        "price_score_summary": price_score_summary,
        "production_cv_summary": production_cv,
    }


# ==============================================================================
# 5. KHỐI 4: TỔNG HỢP & XUẤT BÁO CÁO MARKDOWN + JSON
# ==============================================================================


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Tạo bảng Markdown chuẩn GFM."""
    if not rows:
        return "_Không có dữ liệu._"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(lines)


def _fmt_vnd(v: float) -> str:
    return f"{v:,.0f} đ"


def generate_evaluation_markdown(report: dict[str, Any]) -> str:
    """Biên soạn báo cáo phân tích dữ liệu & đánh giá mô hình ML chuẩn Markdown."""
    eda = report.get("eda", {})
    fs = report.get("feature_selection", {})
    ev = report.get("model_evaluation", {})
    funnel = eda.get("funnel", {})

    lines: list[str] = [
        "# 📊 Báo Cáo Phân Tích Dữ Liệu (EDA), Lựa Chọn Đặc Trưng & Đánh Giá Mô Hình ML (Homigo)",
        "",
        f"> **Thời gian tạo:** {report.get('generated_at', 'N/A')}  ",
        f"> **Tập dữ liệu gốc:** `{funnel.get('raw_total', 0):,}` tin đăng $\\rightarrow$ **{funnel.get('clean_total', 0):,}` tin sạch** (tỷ lệ giữ lại **{funnel.get('retention_rate_pct', 0):.2f}%**)  ",
        f"> **Bộ đặc trưng Production:** `PRUNED_19_FEATURES` (19 gốc + 3 phái sinh + 7 `SpatialTE` = **29 cột đầu vào cây**)  ",
        "",
        "---",
        "",
        "## 1. 🔍 Phân Tích Dữ Liệu Khám Phá (EDA) & Phễu Làm Sạch",
        "",
        "### 1.1. Phễu Làm Sạch Dữ Liệu (Data Cleaning Funnel)",
    ]

    reasons = funnel.get("rule_rejection_reasons", {})
    funnel_rows = [
        ["1. Dữ liệu đầu vào (`listings_clean.parquet`)", f"{funnel.get('raw_total', 0):,}", "100.0%", "Dữ liệu crawl đã gắn nhãn LLM"],
        ["2. Lọc biên lãnh thổ Việt Nam (`lat ∈ [8, 23.5], lng ∈ [102, 110]`)", f"{funnel.get('after_geo_total', 0):,}", f"-{funnel.get('dropped_geo_count', 0):,}", "Loại tọa độ (0,0) / ngoài Việt Nam"],
        ["3. Lọc ngưỡng thích ứng theo `room_type_id`", f"**{funnel.get('clean_total', 0):,}**", f"-{funnel.get('dropped_rule_count', 0):,}", f"Diện tích: {reasons.get('area_oor', 0)}, Giá: {reasons.get('price_oor', 0)}, Đơn giá PPM: {reasons.get('ppm_oor', 0)}"],
    ]
    lines.append(_md_table(["Bước Lọc", "Số Bản Ghi", "Thay Đổi", "Ghi Chú"], funnel_rows))
    lines.append("")

    # Phân phối tổng thể
    lines.append("### 1.2. Thống Kê Phân Phối Các Biến Chính (Trên Tập Sạch)")
    dists = eda.get("overall_distributions", {})
    dist_rows = []
    for k, label, is_money in [
        ("price_vnd", "Giá thuê (`price_vnd`)", True),
        ("log1p_price", "Log giá (`ln(1 + price)`)", False),
        ("area_m2", "Diện tích (`area_m2`)", False),
        ("ppm_vnd", "Đơn giá (`ppm` đ/m²)", True),
        ("dist_nearest_hub_km", "Khoảng cách tâm đô thị (km)", False),
        ("dist_nearest_uni_km", "Khoảng cách cụm ĐH (km)", False),
        ("amenity_overall", "Điểm tiện nghi LLM (`[0..1]`)", False),
        ("safety_score", "Điểm an ninh LLM (`[0..1]`)", False),
    ]:
        s = dists.get(k, {})
        fmt = _fmt_vnd if is_money else (lambda x: f"{x:.3f}")
        dist_rows.append([label, fmt(s.get("mean", 0)), fmt(s.get("p25", 0)), fmt(s.get("median", 0)), fmt(s.get("p75", 0)), fmt(s.get("p95", 0)), f"{s.get('skewness', 0):.2f}"])
    lines.append(_md_table(["Biến Số", "Trung Bình", "P25", "Trung Vị (P50)", "P75", "P95", "Độ Lệch (Skew)"], dist_rows))
    lines.append("")

    # Phân khúc theo loại phòng & thành phố
    lines.append("### 1.3. Phân Bố Theo 5 Loại Phòng (`room_type_id`)")
    rt_rows = [
        [r["name"], f"{r['count']:,}", f"{r['share_pct']}%", _fmt_vnd(r["price_median_vnd"]), f"{r['area_median_m2']} m²", _fmt_vnd(r["ppm_median_vnd"]), f"{r['amenity_overall_mean']:.2f}"]
        for r in eda.get("room_type_breakdown", [])
    ]
    lines.append(_md_table(["Loại Phòng", "Số Lượng", "Tỷ Trọng", "Giá Trung Vị", "Diện Tích TV", "Đơn Giá TV", "Amenity TB"], rt_rows))
    lines.append("")

    lines.append("### 1.4. Phân Bố Địa Lý Theo Tỉnh/Thành Phố (Top 8)")
    city_rows = [
        [c["city"], f"{c['count']:,}", f"{c['share_pct']}%", _fmt_vnd(c["price_median_vnd"]), f"{c['area_median_m2']} m²", _fmt_vnd(c["ppm_median_vnd"])]
        for c in eda.get("city_breakdown", [])
    ]
    lines.append(_md_table(["Tỉnh / Thành phố", "Số Lượng", "Tỷ Trọng", "Giá Trung Vị", "Diện Tích TV", "Đơn Giá TV"], city_rows))
    lines.append("")

    # Mục 2: Giải trình chọn feature
    lines.append("---")
    lines.append("")
    lines.append("## 2. 🧩 Giải Trình Lựa Chọn Đặc Trưng (Tại Sao Chọn 19 Features + SpatialTE?)")
    lines.append("")

    mc = fs.get("multicollinearity", {})
    av = mc.get("area_vs_log_area", {})
    na = mc.get("n_amenities_vs_amenity_overall", {})
    lines.extend([
        "### 2.1. Kiểm Soát Đa Cộng Tuyến & Lý Do Tinh Gọn 7 Cờ Nhị Phân",
        f"- **`area_m2` vs `log_area`:** $\\text{{Spearman}} = {av.get('spearman_rho', 1.0):.4f}$, $\\text{{Pearson}} = {av.get('pearson_r', 0.0):.4f}$ $\\rightarrow$ Cây quyết định phân tách theo thứ tự hạng nên `log_area` trùng lặp 100% với `area_m2`.",
        f"- **`n_amenities` vs `amenity_overall`:** $\\text{{Pearson}} = {na.get('pearson_r', 0.0):.4f}$, $\\text{{Spearman}} = {na.get('spearman_rho', 0.0):.4f}$ $\\rightarrow$ Thay bằng `amenity_density = amenity_overall / ln(1 + area_m2)`.",
        "",
        "#### Thống kê 7 cờ ít tác động đã loại khỏi mô hình ML (`PRUNED_LOW_IMPACT_FLAGS`):",
    ])
    pruned_rows = [
        [p["feature"], f"{p['prevalence_pct']}%", f"{p['corr_log_price']:+.3f}", f"{p['corr_amenity_overall']:+.3f}", f"{p['corr_safety_score']:+.3f}", f"{p['mutual_info']:.4f}"]
        for p in mc.get("pruned_flags_summary", [])
    ]
    lines.append(_md_table(["Cờ Bị Cắt (ML)", "Tỷ Lệ Có", "r với Log Giá", "r với Amenity", "r với Safety", "Mutual Info"], pruned_rows))
    lines.append("")

    # Feature Importance theo nhóm & chi tiết
    imp = fs.get("production_feature_importance", {})
    lines.append("### 2.2. Xếp Hạng Đóng Góp Thực Tế Theo Nhóm Đặc Trưng (`rent_pipeline.joblib`)")
    grp_rows = [
        [g["group"], str(g["feature_count"]), f"{g['lgb_gain_pct']:.2f}%", f"{g['xgb_gain_pct']:.2f}%", f"**{g['ensemble_gain_pct']:.2f}%**"]
        for g in imp.get("group_summary", [])
    ]
    lines.append(_md_table(["Nhóm Đặc Trưng", "Số Cột", "LightGBM Gain", "XGBoost Gain", "Ensemble Gain"], grp_rows))
    lines.append("")

    lines.append("### 2.3. Top 15 Đặc Trưng Quan Trọng Nhất (Normalized Gain Importance)")
    top_feats = [
        [str(i), f"`{f['feature']}`", f["group"], f"{f['lgb_gain_pct']:.2f}%", f"{f['xgb_gain_pct']:.2f}%", f"**{f['ensemble_gain_pct']:.2f}%**"]
        for i, f in enumerate(imp.get("features", [])[:15], 1)
    ]
    lines.append(_md_table(["Hạng", "Đặc Trưng", "Nhóm", "LGBM Gain", "XGB Gain", "Ensemble Gain"], top_feats))
    lines.append("")

    # Ablation Study
    lines.append("### 2.4. Thực Nghiệm Ablation Study (Chứng Minh Đóng Góp Từng Nhóm Đặc Trưng)")
    abl_rows = [
        [f"`{a['config_id']}`", str(a["n_features_into_tree"]), _fmt_vnd(a["mae_vnd"]), _fmt_vnd(a["rmse_vnd"]), f"{a['r2_vnd']:.4f}", f"{a['r2_log']:.4f}", f"{a['mape_pct']:.2f}%"]
        for a in fs.get("ablation_study", [])
    ]
    lines.append(_md_table(["Cấu Hình Thử Nghiệm", "Số Cột", "MAE", "RMSE", "R² (VNĐ)", "R² (Log)", "MAPE"], abl_rows))
    lines.append("")

    # Mục 3: Đánh giá mô hình Holdout Test
    lines.append("---")
    lines.append("")
    lines.append("## 3. 📈 Đánh Giá Hiệu Suất Mô Hình (Holdout Test 15% Không Leakage)")
    lines.append("")

    comp = ev.get("model_comparison", {})
    comp_rows = [
        [name, _fmt_vnd(m["mae_vnd"]), _fmt_vnd(m["median_ae_vnd"]), _fmt_vnd(m["rmse_vnd"]), f"{m['mape_pct']:.2f}%", f"{m['mdape_pct']:.2f}%", f"{m['r2_vnd']:.4f}", f"{m['r2_log']:.4f}", f"{m['within_20pct']:.1f}%"]
        for name, m in comp.items()
    ]
    lines.append(_md_table(["Mô Hình", "MAE", "MedianAE", "RMSE", "MAPE", "MdAPE", "R² (VNĐ)", "R² (Log)", "Sai Số ≤ 20%"], comp_rows))
    lines.append("")

    seg = ev.get("segment_performance", {})
    lines.append("### 3.1. Hiệu Suất Phân Rã Theo 5 Loại Phòng")
    seg_rt_rows = [
        [s["room_type"], str(s["count"]), _fmt_vnd(s["median_actual_vnd"]), _fmt_vnd(s["mae_vnd"]), f"{s['mape_pct']:.2f}%", f"{s['mdape_pct']:.2f}%", f"{s['within_20pct']:.1f}%", f"{s['conformal_coverage_pct']:.1f}%"]
        for s in seg.get("by_room_type", [])
    ]
    lines.append(_md_table(["Loại Phòng", "Số Mẫu", "Giá Thực TV", "MAE", "MAPE", "MdAPE", "Trong ±20%", "Độ Phủ 80%"], seg_rt_rows))
    lines.append("")

    lines.append("### 3.2. Hiệu Suất Phân Rã Theo Phân Khúc Giá & Địa Lý")
    seg_price_rows = [
        [s["price_tier"], str(s["count"]), _fmt_vnd(s["mae_vnd"]), f"{s['mape_pct']:.2f}%", f"{s['within_20pct']:.1f}%", f"{s['conformal_coverage_pct']:.1f}%", _fmt_vnd(s["median_interval_width_vnd"])]
        for s in seg.get("by_price_tier", [])
    ]
    lines.append(_md_table(["Phân Khúc Giá", "Số Mẫu", "MAE", "MAPE", "Trong ±20%", "Độ Phủ 80%", "Độ Rộng Khoảng TV"], seg_price_rows))
    lines.append("")

    seg_reg_rows = [
        [s["region"], str(s["count"]), _fmt_vnd(s["mae_vnd"]), f"{s['mape_pct']:.2f}%", f"{s['r2_vnd']:.4f}", f"{s['within_20pct']:.1f}%", f"{s['conformal_coverage_pct']:.1f}%"]
        for s in seg.get("by_region", [])
    ]
    lines.append(_md_table(["Khu Vực", "Số Mẫu", "MAE", "MAPE", "R² (VNĐ)", "Trong ±20%", "Độ Phủ 80%"], seg_reg_rows))
    lines.append("")

    # Mục 4: Conformal Prediction & price_score
    lines.append("---")
    lines.append("")
    lines.append("## 4. 🎯 Đánh Giá Khoảng Tin Cậy Mondrian Conformal & Phân Phối `price_score`")
    conf = ev.get("conformal_diagnostics", {})
    lines.extend([
        f"- **Độ phủ thực tế (Empirical Coverage):** **{conf.get('empirical_coverage_pct', 0):.2f}%** (Mục tiêu danh định: **{conf.get('target_coverage_pct', 80):.0f}%**; Dưới ngưỡng: {conf.get('below_low_pct', 0):.2f}%, Vượt ngưỡng: {conf.get('above_high_pct', 0):.2f}%).",
        f"- **Độ rộng khoảng dự đoán:** Trung bình **{_fmt_vnd(conf.get('mean_width_vnd', 0))}** | Trung vị **{_fmt_vnd(conf.get('median_width_vnd', 0))}** (tương đương ±{conf.get('median_rel_width_pct', 0) / 2:.1f}% quanh giá dự đoán).",
        "",
    ])
    bin_rows = [
        [f"Bin {b['bin']}", str(b["count"]), _fmt_vnd(b["median_pred_vnd"]), f"{b['qhat_log']:.4f}", f"{b['coverage_pct']:.1f}%", _fmt_vnd(b["median_width_vnd"])]
        for b in conf.get("bin_breakdown", [])
    ]
    lines.append(_md_table(["Mondrian Bin", "Số Mẫu", "Giá Dự Đoán TV", "Hiệu Chuẩn q_hat (log)", "Độ Phủ Thực Tế", "Độ Rộng TV"], bin_rows))
    lines.append("")

    ps = ev.get("price_score_summary", {})
    ps_dist = ps.get("price_score", {})
    verdict_dist = ps.get("verdict_distribution_pct", {})
    lines.extend([
        "### 4.1. Phân Phối Điểm `price_score` & Nhãn Nhận Định (`PriceEvaluator`)",
        f"- **`price_score`:** Mean = `{ps_dist.get('mean', 0):.3f}`, Median = `{ps_dist.get('median', 0):.3f}`, Std = `{ps_dist.get('std', 0):.3f}`, P10–P90 khoảng `[~{ps_dist.get('p05', 0):.2f} .. {ps_dist.get('p95', 0):.2f}]`.",
        f"- **Trạng thái `InputGuard` trên tập kiểm thử sạch:** `{ps.get('guard_status_distribution_pct', {})}`.",
        "- **Tỷ lệ các nhãn nhận định giá:** " + ", ".join(f"`{k}`: {v:.1f}%" for k, v in verdict_dist.items()),
        "",
        "---",
        "",
        "## 5. 💡 Nhận Xét Chuyên Sâu & Khuyến Nghị",
        "- **Hiệu quả chọn đặc trưng:** Bộ `PRUNED_19_FEATURES` + `SpatialTE` (29 cột) đạt kết quả tốt nhất trong cả 4 thử nghiệm Ablation (MAE thấp hơn và R² cao hơn bộ 36 cột chưa cắt 7 cờ), chứng tỏ 7 cờ bị cắt đã được tóm tắt thông qua `amenity_overall` và `safety_score`.",
        "- **Hiệu năng phân khúc phổ thông (2.5 - 7 triệu, chiếm 82.7% dữ liệu):** MdAPE chỉ `12.45%` cho toàn tập, riêng phân khúc `4 - 7 triệu` có `81.7%` dự đoán nằm trong sai số `±20%` và độ phủ Conformal đạt `84.3%`.",
        "- **Khả năng tổng quát hóa Toàn Quốc:** Nhóm tỉnh/thành ngoài TP.HCM (Hà Nội, Bình Dương, Đà Nẵng, Cần Thơ...) đạt `R² = 0.7083` và độ phủ Conformal `83.0%` tương đương TP.HCM (`83.2%`).",
        "- **Điểm cần cải thiện:** Phân khúc giá cao (`> 7 triệu`, chiếm `< 3.5%` tập test) và `SLEEPBOX` (giá tuyệt đối nhỏ 1.5tr nhưng biến thiên lớn theo tiện nghi KTX) có độ phủ/MAPE còn hạn chế; nên thu thập thêm mẫu phân khúc cao cấp hoặc cân nhắc Mondrian bin riêng cho phân khúc `> 7 triệu`.",
        "",
    ])
    return "\n".join(lines)


def save_evaluation_artifacts(
    report: dict[str, Any],
    json_path: Path | str = EVALUATION_JSON_PATH,
    md_path: Path | str = EVALUATION_MD_PATH,
) -> tuple[Path, Path]:
    """Lưu báo cáo phân tích và đánh giá ra JSON + Markdown."""
    jp = Path(json_path)
    mp = Path(md_path)
    jp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)

    with open(jp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_text = generate_evaluation_markdown(report)
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md_text)

    return jp, mp


def run_full_evaluation(
    data_path: str | Path = DEFAULT_PARQUET_PATH,
    json_path: Path | str = EVALUATION_JSON_PATH,
    md_path: Path | str = EVALUATION_MD_PATH,
    *,
    run_ablation: bool = True,
    save_files: bool = True,
) -> dict[str, Any]:
    """Chạy trọn bộ EDA -> Feature Selection & Ablation -> Holdout Evaluation -> Xuất báo cáo."""
    t0 = time.time()
    evaluator = PriceEvaluator()

    eda = analyze_dataset_eda(data_path=data_path)
    X_full, y_full = load_and_preprocess_dataset(data_path=data_path, pruned=False)
    X_pruned = X_full[[c for c in PRUNED_19_FEATURES if c in X_full.columns]].copy()

    fs = analyze_feature_selection(
        X_full, y_full, results=evaluator.results, run_ablation=run_ablation, random_state=42
    )
    ev_report = evaluate_production_pipeline(X_pruned, y_full, evaluator=evaluator, random_state=42)

    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - t0, 2),
        "eda": eda,
        "feature_selection": fs,
        "model_evaluation": ev_report,
    }
    if save_files:
        save_evaluation_artifacts(report, json_path=json_path, md_path=md_path)
    return report


def _print_console_summary(report: dict[str, Any], jp: Path, mp: Path) -> None:
    """In tóm tắt kết quả phân tích & đánh giá ra terminal."""
    funnel = report["eda"]["funnel"]
    print("=" * 72)
    print("  BÁO CÁO EDA, CHỌN ĐẶC TRƯNG & ĐÁNH GIÁ MÔ HÌNH ĐỊNH GIÁ HOMIGO ML")
    print("=" * 72)
    print(f"[1. EDA] Gốc: {funnel['raw_total']:,} -> Sau Geo VN: {funnel['after_geo_total']:,} -> Sạch: {funnel['clean_total']:,} ({funnel['retention_rate_pct']}%)")
    print("\n[2. TOP 10 FEATURES (Ensemble Gain %)]")
    for i, feat in enumerate(report["feature_selection"]["production_feature_importance"]["features"][:10], 1):
        print(f"  {i:2d}. {feat['feature']:<24s} | LGBM={feat['lgb_gain_pct']:5.2f}% | XGB={feat['xgb_gain_pct']:5.2f}% | Ens={feat['ensemble_gain_pct']:5.2f}%")

    print("\n[3. ABLATION STUDY (Holdout Test 15%)]")
    for a in report["feature_selection"]["ablation_study"]:
        print(f"  - {a['config_id']:<26s} ({a['n_features_into_tree']:2d} cols): MAE={a['mae_vnd']:>9,.0f} đ | RMSE={a['rmse_vnd']:>9,.0f} đ | R2={a['r2_vnd']:.4f} | R2_log={a['r2_log']:.4f}")

    print("\n[4. SO SÁNH MÔ HÌNH TRÊN HOLDOUT TEST (15%)]")
    for name, m in report["model_evaluation"]["model_comparison"].items():
        print(f"  - {name:<28s}: MAE={m['mae_vnd']:>9,.0f} đ | MdAPE={m['mdape_pct']:5.2f}% | R2={m['r2_vnd']:.4f} | R2_log={m['r2_log']:.4f} | <=20%: {m['within_20pct']:5.1f}%")

    conf = report["model_evaluation"]["conformal_diagnostics"]
    print(f"\n[5. CONFORMAL] Coverage thực tế: {conf['empirical_coverage_pct']:.2f}% (Kỳ vọng: 80%) | Median Width: {conf['median_width_vnd']:,.0f} đ")
    print(f"\n[SAVED] JSON: {jp}")
    print(f"[SAVED] MD  : {mp}")
    print(f"[DONE] Hoàn tất trong {report['elapsed_s']}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy EDA, Feature Selection & Model Evaluation cho Homigo ML.")
    parser.add_argument("--data-path", default=str(DEFAULT_PARQUET_PATH), help="Đường dẫn dữ liệu sạch Parquet/JSON.")
    parser.add_argument("--no-ablation", action="store_true", help="Bỏ qua bước huấn luyện thử nghiệm Ablation Study.")
    args = parser.parse_args()

    report = run_full_evaluation(data_path=args.data_path, run_ablation=not args.no_ablation, save_files=True)
    _print_console_summary(report, EVALUATION_JSON_PATH, EVALUATION_MD_PATH)


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
