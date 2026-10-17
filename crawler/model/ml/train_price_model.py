"""
ml/train_price_model.py
Pipeline huấn luyện mô hình dự đoán giá thuê phòng trọ (Homigo).

Kiến trúc mô hình:
1. Feature Engineering: Biến đổi log diện tích, tương quan tọa độ, tổng số tiện ích.
2. Spatial Target Encoding (SpatialTE): Dùng BallTree (haversine) trích xuất thống kê giá láng giềng.
3. Model Blend: LightGBM + XGBoost được tối ưu siêu tham số tự động bằng Optuna (5-Fold CV).
4. Smearing Retransformation Bias Correction: Khử lệch khi chuyển từ log-price về VND.
5. Mondrian Conformal Prediction (CQR): Sinh khoảng tin cậy [low, high] với độ phủ danh định 80%.
6. InputGuard: Bảo vệ biên dữ liệu và phát hiện bất thường khi suy luận.
"""

from __future__ import annotations
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split
import xgboost as xgb

ML_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ML_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crawler.model.ml.feature_extractor import load_and_preprocess_dataset
from crawler.model.ml.models import (
    DROP_COLS,
    FINAL_PREDICT,
    MAX_PRICE,
    PPM_RANGE,
    InputGuard,
    MondrianPriceInterval,
    PriceInterval,
    SpatialTE,
    attach,
    blend_predict,
    make_base_features,
    predict_log,
)

# Tắt log cảnh báo thừa
optuna.logging.set_verbosity(optuna.logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)

ARTIFACTS_DIR = ML_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

METRIC_LABELS = {"mse": "MSE", "mae": "MAE", "rmse": "RMSE", "r2": "R²"}


# ----------------------------------------------------------------------------
# 1. Đánh giá & Metrics
# ----------------------------------------------------------------------------
def evaluate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_pred = np.clip(y_pred, 0, None)
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mse": float(mse),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_true, y_pred)),
    }


# ----------------------------------------------------------------------------
# 2. Định nghĩa cấu hình Models (LightGBM & XGBoost)
# ----------------------------------------------------------------------------
models_config = {
    "LightGBM": {
        "fixed_params": {
            "objective": "regression",
            "metric": "rmse",
            "seed": 42,
            "n_jobs": 4,
            "verbose": -1,
            "subsample_freq": 1,
            "max_depth": -1,
        },
        "param_fn": lambda t: {
            "learning_rate": t.suggest_float("learning_rate", 0.015, 0.08, log=True),
            "num_leaves": t.suggest_int("num_leaves", 20, 90),
            "min_child_samples": t.suggest_int("min_child_samples", 10, 80),
            "subsample": t.suggest_float("subsample", 0.7, 1.0),
            "colsample_bytree": t.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": t.suggest_float("reg_lambda", 1e-2, 20.0, log=True),
            "min_split_gain": t.suggest_float("min_split_gain", 1e-3, 0.5, log=True),
        },
        "train_fn": lambda p, Xt, yt, Xv, yv: lgb.train(
            p,
            lgb.Dataset(Xt, yt),
            num_boost_round=1500,
            valid_sets=[lgb.Dataset(Xv, yv)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        ),
        "best_iter_fn": lambda m: m.best_iteration,
        "predict_fn": lambda m, X: m.predict(X, num_iteration=m.best_iteration),
        "fit_full_fn": lambda p, X, y, n: lgb.train(
            p, lgb.Dataset(X, y), num_boost_round=n
        ),
    },
    "XGBoost": {
        "fixed_params": {
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
            "tree_method": "hist",
            "seed": 42,
            "nthread": 4,
        },
        "param_fn": lambda t: {
            "learning_rate": t.suggest_float("learning_rate", 0.015, 0.08, log=True),
            "max_depth": t.suggest_int("max_depth", 5, 10),
            "min_child_weight": t.suggest_float("min_child_weight", 1.0, 15.0, log=True),
            "subsample": t.suggest_float("subsample", 0.7, 1.0),
            "colsample_bytree": t.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": t.suggest_float("reg_lambda", 1e-2, 20.0, log=True),
            "gamma": t.suggest_float("gamma", 1e-3, 0.5, log=True),
        },
        "train_fn": lambda p, Xt, yt, Xv, yv: xgb.train(
            p,
            xgb.DMatrix(Xt, yt, enable_categorical=True),
            num_boost_round=1500,
            evals=[(xgb.DMatrix(Xv, yv, enable_categorical=True), "val")],
            early_stopping_rounds=50,
            verbose_eval=False,
        ),
        "best_iter_fn": lambda m: m.best_iteration + 1,
        "predict_fn": lambda m, X: m.predict(
            xgb.DMatrix(X, enable_categorical=True),
            iteration_range=(0, m.best_iteration + 1),
        ),
        "fit_full_fn": lambda p, X, y, n: xgb.train(
            p, xgb.DMatrix(X, y, enable_categorical=True), num_boost_round=n
        ),
    },
}


# ----------------------------------------------------------------------------
# 3. Huấn luyện Optuna với K-Fold CV
# ----------------------------------------------------------------------------
def _build_folds(X, y, kf, es_frac=0.15, random_state=42, ks=(5, 20), winsor=(0.01, 0.99)):
    folds = []
    for tr_idx, val_idx in kf.split(X, y):
        fit_idx, es_idx = train_test_split(
            tr_idx, test_size=es_frac, random_state=random_state
        )
        te = SpatialTE(ks).fit(X.iloc[fit_idx], y.iloc[fit_idx])
        y_fit = y.iloc[fit_idx]
        y_fit = y_fit.clip(y_fit.quantile(winsor[0]), y_fit.quantile(winsor[1]))
        folds.append({
            "Xf": attach(X.iloc[fit_idx], te.transform_train(X.iloc[fit_idx])),
            "Xe": attach(X.iloc[es_idx], te.transform(X.iloc[es_idx])),
            "Xv": attach(X.iloc[val_idx], te.transform(X.iloc[val_idx])),
            "yf": np.log1p(y_fit.values),
            "ye": np.log1p(y.iloc[es_idx].values),
            "y_val": y.iloc[val_idx].values,
        })
    return folds


def train_models_optuna(
    X_raw: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
    n_trials: int = 25,
    random_state: int = 42,
    winsor: Tuple[float, float] = (0.01, 0.99),
    ks: Tuple[int, int] = (5, 20),
) -> List[Dict[str, Any]]:
    y = pd.Series(np.asarray(y, dtype=float).ravel())
    X = make_base_features(X_raw).reset_index(drop=True)

    kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    print(f"[OPTUNA] Đang tính toán feature láng giềng SpatialTE cho {n_splits} folds...")
    folds = _build_folds(X, y, kf, 0.15, random_state, ks, winsor)

    y_clip = y.clip(y.quantile(winsor[0]), y.quantile(winsor[1]))
    results = []

    for model_name, config in models_config.items():
        print(f"\n[OPTUNA] Bắt đầu tuning: {model_name} ({n_trials} trials)...")

        def objective(trial):
            params = {**config["fixed_params"], **config["param_fn"](trial)}
            cvm = {k: [] for k in METRIC_LABELS}
            best_iters, resid = [], []

            for f in folds:
                model = config["train_fn"](params, f["Xf"], f["yf"], f["Xe"], f["ye"])
                best_iters.append(config["best_iter_fn"](model))
                pred_log = config["predict_fn"](model, f["Xv"])
                resid.append(np.log1p(f["y_val"]) - pred_log)
                for k, v in evaluate_metrics(f["y_val"], np.expm1(pred_log)).items():
                    cvm[k].append(v)

            trial.set_user_attr("cv_metrics", cvm)
            trial.set_user_attr("best_iters", best_iters)
            trial.set_user_attr("smear", float(np.mean(np.exp(np.concatenate(resid)))))
            return float(np.mean(cvm["mae"]))

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=random_state),
        )
        study.optimize(objective, n_trials=n_trials)

        bt = study.best_trial
        n_rounds = int(np.mean(bt.user_attrs["best_iters"]) * 1.1)
        full_params = {**config["fixed_params"], **study.best_params}

        # Train model cuối trên toàn bộ dữ liệu
        te = SpatialTE(ks).fit(X, y)
        X_full = attach(X, te.transform_train(X))
        final_model = config["fit_full_fn"](
            full_params, X_full, np.log1p(y_clip.values), n_rounds
        )

        res = {
            "model_name": model_name,
            "best_estimator": final_model,
            "best_params": full_params,
            "n_rounds": n_rounds,
            "fe": te,
            "smear": bt.user_attrs["smear"],
            "ks": ks,
        }
        for k, v in bt.user_attrs["cv_metrics"].items():
            res[f"{k}_mean"], res[f"{k}_std"] = float(np.mean(v)), float(np.std(v))

        results.append(res)
        print(
            f"  --> {model_name}: MAE = {res['mae_mean']:,.0f} đ | "
            f"RMSE = {res['rmse_mean']:,.0f} đ | R² = {res['r2_mean']:.4f} | smear = {res['smear']:.3f}"
        )

    return results


# ----------------------------------------------------------------------------
# 4. Main Workflow Huấn luyện
# ----------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("   KHỞI ĐỘNG HUẤN LUYỆN MÔ HÌNH ĐỊNH GIÁ HOMIGO ML")
    print("=" * 60)

    # 1. Nạp và tiền xử lý dữ liệu theo Schema mới
    X, y = load_and_preprocess_dataset()
    print(f"[DATA] Đã nạp thành công {len(X)} bản ghi sạch.")
    print(f"[DATA] Danh sách {len(X.columns)} features đầu vào: {X.columns.tolist()}")

    # 2. Train-test split (85% train, 15% test)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    # 3. Chạy Optuna tuning
    t0 = time.time()
    results = train_models_optuna(X_train, y_train, n_splits=5, n_trials=25, random_state=42)

    # 4. Huấn luyện khoảng giá Mondrian Conformal Prediction
    print("\n[INTERVAL] Đang huấn luyện mô hình khoảng giá Mondrian Conformal Prediction (80%)...")
    lgb_res = next(r for r in results if r["model_name"] == "LightGBM")
    pi = MondrianPriceInterval(lgb_res, n_bins=4, coverage=0.8, seed=42).fit(X_train, y_train)

    # 5. Huấn luyện InputGuard
    guard = InputGuard().fit(X_train)

    # 6. Đánh giá trên tập test độc lập
    print("\n" + "=" * 60)
    print("   KẾT QUẢ ĐÁNH GIÁ TRÊN TẬP TEST ĐỘC LẬP (15%)")
    print("=" * 60)
    p_blend = blend_predict(results, X_test)
    test_metrics = evaluate_metrics(y_test.values, p_blend)
    print(f"  * MAE  : {test_metrics['mae']:,.0f} VNĐ")
    print(f"  * RMSE : {test_metrics['rmse']:,.0f} VNĐ")
    print(f"  * R²   : {test_metrics['r2']:.4f}")

    # Đánh giá độ phủ khoảng giá
    rng_test = pi.predict(X_test)
    in_interval = (y_test.values >= rng_test["low"]) & (y_test.values <= rng_test["high"])
    actual_coverage = np.mean(in_interval)
    print(f"  * Conformal Coverage thực tế : {actual_coverage * 100:.1f}% (Kỳ vọng: 80%)")
    print(f"  * Thời gian huấn luyện tổng : {time.time() - t0:.1f}s")

    # 7. Huấn luyện lần cuối trên toàn bộ dữ liệu (Full dataset) để triển khai thực tế
    print("\n[EXPORT] Huấn luyện pipeline hoàn chỉnh trên toàn bộ dữ liệu sạch để xuất xưởng...")
    results_full = train_models_optuna(X, y, n_splits=5, n_trials=15, random_state=42)
    lgb_full = next(r for r in results_full if r["model_name"] == "LightGBM")
    pi_full = MondrianPriceInterval(lgb_full, n_bins=4, coverage=0.8, seed=42).fit(X, y)
    guard_full = InputGuard().fit(X)

    # 8. Lưu Artifacts
    pipeline_path = ARTIFACTS_DIR / "rent_pipeline.joblib"
    guard_path = ARTIFACTS_DIR / "guard.joblib"
    metrics_path = ARTIFACTS_DIR / "training_metrics.json"

    bundle = {
        "results": results_full,
        "interval": pi_full,
        "features_in": X.columns.tolist(),
        "test_metrics": test_metrics,
        "coverage": actual_coverage,
    }
    joblib.dump(bundle, pipeline_path, compress=3)
    joblib.dump(guard_full, guard_path)

    report = {
        "dataset_size": len(X),
        "features": X.columns.tolist(),
        "mae_vnd": round(test_metrics["mae"], 2),
        "rmse_vnd": round(test_metrics["rmse"], 2),
        "r2_score": round(test_metrics["r2"], 4),
        "conformal_coverage": round(actual_coverage, 4),
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[SUCCESS] Đã lưu pipeline tại: {pipeline_path}")
    print(f"[SUCCESS] Đã lưu guard tại: {guard_path}")
    print(f"[SUCCESS] Đã lưu báo cáo metrics tại: {metrics_path}")


if __name__ == "__main__":
    main()
