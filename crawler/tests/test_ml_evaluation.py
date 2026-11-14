"""
tests/test_ml_evaluation.py
Bộ kiểm thử hộp đen độc lập 4 nhóm cho module Phân tích Dữ liệu (EDA),
Giải trình Lựa chọn Đặc trưng & Đánh giá Mô hình ML (`crawler/model/ml/evaluate_model.py`).
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest

from crawler.config.paths import ML_ARTIFACTS_DIR
from crawler.model.ml.evaluate_model import (
    EVALUATION_JSON_PATH,
    EVALUATION_MD_PATH,
    analyze_dataset_eda,
    analyze_feature_selection,
    compute_regression_metrics,
    evaluate_production_pipeline,
    generate_evaluation_markdown,
    save_evaluation_artifacts,
)
from crawler.model.ml.feature_extractor import (
    ALL_BINARY_KEYS,
    PRUNED_19_FEATURES,
    PRUNED_LOW_IMPACT_FLAGS,
    extract_features_from_record,
)
from crawler.model.ml.price_evaluator import PriceEvaluator


def _make_synthetic_dataset(n: int = 120, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Tạo tập dữ liệu giả lập đa phân khúc & đa tỉnh thành để kiểm thử nhanh."""
    rng = np.random.default_rng(seed)
    cities = [
        ("Tp Hồ Chí Minh", 10.7725, 106.6980),
        ("Hà Nội", 21.0285, 105.8542),
        ("Đà Nẵng", 16.0618, 108.2208),
    ]
    rows = []
    for i in range(n):
        city, base_lat, base_lng = cities[i % len(cities)]
        rt_id = (i % 5) + 1
        area = float(rng.uniform(16.0, 45.0)) if rt_id != 4 else float(rng.uniform(15.0, 35.0))
        base_price = {1: 3_000_000, 2: 4_500_000, 3: 6_500_000, 4: 1_400_000, 5: 8_000_000}[rt_id]
        price = float(base_price + area * 65_000 + rng.normal(0, 250_000))
        price = max(800_000.0, price)
        rec = {
            "listing_id": f"syn_{i}",
            "city": city,
            "lat": base_lat + float(rng.normal(0, 0.02)),
            "lng": base_lng + float(rng.normal(0, 0.02)),
            "area_m2": area,
            "price_vnd": price,
            "room_type_id": rt_id,
            "furnishing_code": 1 if i % 2 == 0 else 2,
            "amenity_overall": float(rng.uniform(0.2, 0.9)),
            "safety_score": float(rng.uniform(0.1, 0.9)),
        }
        for k in ALL_BINARY_KEYS:
            rec[k] = bool((i + hash(k)) % 3 == 0)
        rows.append(rec)

    raw_df = pd.DataFrame(rows)
    extracted = pd.DataFrame([extract_features_from_record(r) for r in rows])
    y = extracted["price_vnd"].copy()
    X_full = extracted.drop(columns=["listing_id", "price_vnd"]).copy()
    return raw_df, X_full, y


# ==============================================================================
# NHÓM 1: HAPPY PATH
# ==============================================================================


class TestMLEvaluationHappyPath:
    """Kiểm tra luồng chuẩn của EDA, Feature Selection & Model Evaluation."""

    def test_analyze_dataset_eda_structure_and_funnel(self):
        raw_df, _, _ = _make_synthetic_dataset(n=60)
        # Chèn thêm 2 bản ghi lỗi để kiểm tra phễu lọc
        bad_geo = raw_df.iloc[0].to_dict()
        bad_geo["listing_id"] = "bad_geo"
        bad_geo["lat"] = 0.0
        bad_geo["lng"] = 0.0

        bad_area = raw_df.iloc[1].to_dict()
        bad_area["listing_id"] = "bad_area"
        bad_area["area_m2"] = 1.0
        bad_area["room_type_id"] = 1

        df_in = pd.concat([raw_df, pd.DataFrame([bad_geo, bad_area])], ignore_index=True)
        eda = analyze_dataset_eda(raw_df=df_in)

        funnel = eda["funnel"]
        assert funnel["raw_total"] == 62
        assert funnel["after_geo_total"] == 61
        assert funnel["dropped_geo_count"] == 1
        assert funnel["clean_total"] <= 60
        assert 0.0 < funnel["retention_rate_pct"] <= 100.0
        assert "price_vnd" in eda["overall_distributions"]
        assert len(eda["room_type_breakdown"]) == 5
        assert len(eda["binary_flag_prevalence"]) == len(ALL_BINARY_KEYS)

    def test_analyze_feature_selection_with_production_importances(self):
        _, X_full, y = _make_synthetic_dataset(n=120)
        evaluator = PriceEvaluator()
        fs = analyze_feature_selection(X_full, y, results=evaluator.results, run_ablation=True, random_state=42)

        assert len(fs["candidate_feature_stats"]) == 36  # 26 gốc + 3 phái sinh + 7 SpatialTE
        mc = fs["multicollinearity"]
        assert mc["area_vs_log_area"]["spearman_rho"] > 0.99
        assert len(mc["pruned_flags_summary"]) == len(PRUNED_LOW_IMPACT_FLAGS)

        imp = fs["production_feature_importance"]
        assert len(imp["features"]) == 29
        total_ens_gain = sum(f["ensemble_gain_pct"] for f in imp["features"])
        assert 99.0 <= total_ens_gain <= 101.0

        abl = fs["ablation_study"]
        assert [row["config_id"] for row in abl] == [
            "1_Base_19_No_SpatialTE",
            "2_SpatialTE_Only",
            "3_Full_26_With_SpatialTE",
            "4_Pruned_19_With_SpatialTE",
        ]

    def test_evaluate_production_pipeline_on_synthetic_data(self):
        _, X_full, y = _make_synthetic_dataset(n=140)
        X_pruned = X_full[[c for c in PRUNED_19_FEATURES if c in X_full.columns]].copy()
        evaluator = PriceEvaluator()

        ev_res = evaluate_production_pipeline(X_pruned, y, evaluator=evaluator, random_state=42)
        assert set(ev_res["model_comparison"].keys()) == {
            "Baseline (Room-Type Median)",
            "LightGBM (Holdout)",
            "XGBoost (Holdout)",
            "Ensemble Blend (LGBM + XGB)",
        }
        conf = ev_res["conformal_diagnostics"]
        assert 0.0 <= conf["empirical_coverage_pct"] <= 100.0
        assert conf["median_width_vnd"] >= 0.0
        assert len(ev_res["segment_performance"]["by_room_type"]) >= 1
        assert "price_score" in ev_res["price_score_summary"]


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================


class TestMLEvaluationEdgeCases:
    """Kiểm tra chịu lỗi khi tập dữ liệu rỗng, chỉ có 1 mẫu, hoặc toàn bộ bị lọc."""

    def test_compute_regression_metrics_empty_and_single_item(self):
        empty_res = compute_regression_metrics(np.array([]), np.array([]))
        assert empty_res["count"] == 0
        assert empty_res["mae_vnd"] == 0.0
        assert empty_res["r2_vnd"] == 0.0

        single_res = compute_regression_metrics(np.array([3_000_000.0]), np.array([3_300_000.0]))
        assert single_res["count"] == 1
        assert single_res["mae_vnd"] == 300_000.0
        assert single_res["mape_pct"] == 10.0
        assert single_res["within_15pct"] == 100.0
        assert single_res["r2_vnd"] == 0.0

    def test_analyze_eda_when_all_rows_filtered_out(self):
        bad_df = pd.DataFrame([
            {"listing_id": "bad1", "lat": 0.0, "lng": 0.0, "price_vnd": 3_000_000, "area_m2": 20.0},
            {"listing_id": "bad2", "lat": -5.0, "lng": 10.0, "price_vnd": 3_000_000, "area_m2": 20.0},
        ])
        eda = analyze_dataset_eda(raw_df=bad_df)
        assert eda["funnel"]["raw_total"] == 2
        assert eda["funnel"]["clean_total"] == 0
        assert eda["funnel"]["retention_rate_pct"] == 0.0
        assert eda["room_type_breakdown"] == []


# ==============================================================================
# NHÓM 3: STATE MUTATION & ANTI-MODIFICATION
# ==============================================================================


class TestMLEvaluationImmutability:
    """Đảm bảo quá trình phân tích không làm biến đổi DataFrame đầu vào hay artifacts model."""

    def test_input_dataframe_not_mutated_and_model_artifacts_untouched(self):
        _, X_full, y = _make_synthetic_dataset(n=100)
        X_snapshot = X_full.copy(deep=True)
        y_snapshot = y.copy(deep=True)

        pipe_path = ML_ARTIFACTS_DIR / "rent_pipeline.joblib"
        guard_path = ML_ARTIFACTS_DIR / "guard.joblib"
        pipe_mtime_before = pipe_path.stat().st_mtime
        guard_mtime_before = guard_path.stat().st_mtime

        evaluator = PriceEvaluator()
        _ = analyze_feature_selection(X_full, y, results=evaluator.results, run_ablation=False)
        X_pruned = X_full[[c for c in PRUNED_19_FEATURES if c in X_full.columns]].copy()
        _ = evaluate_production_pipeline(X_pruned, y, evaluator=evaluator)

        pd.testing.assert_frame_equal(X_full, X_snapshot)
        pd.testing.assert_series_equal(y, y_snapshot)
        assert pipe_path.stat().st_mtime == pipe_mtime_before
        assert guard_path.stat().st_mtime == guard_mtime_before


# ==============================================================================
# NHÓM 4: PERSISTENCE & SAVED REPORT VERIFICATION
# ==============================================================================


class TestMLEvaluationPersistence:
    """Kiểm tra lưu xuất báo cáo tạm và đối soát artifacts evaluation_report thực tế."""

    def test_save_evaluation_artifacts_creates_valid_json_and_md(self, tmp_path):
        raw_df, X_full, y = _make_synthetic_dataset(n=100)
        evaluator = PriceEvaluator()
        eda = analyze_dataset_eda(raw_df=raw_df)
        fs = analyze_feature_selection(X_full, y, results=evaluator.results, run_ablation=False)
        ev_res = evaluate_production_pipeline(X_full[PRUNED_19_FEATURES], y, evaluator=evaluator)

        payload = {
            "generated_at": "2026-11-14 00:00:00",
            "elapsed_s": 1.2,
            "eda": eda,
            "feature_selection": fs,
            "model_evaluation": ev_res,
        }
        jp, mp = save_evaluation_artifacts(
            payload,
            json_path=tmp_path / "report.json",
            md_path=tmp_path / "report.md",
        )
        assert jp.exists() and mp.exists()
        loaded = json.loads(jp.read_text(encoding="utf-8"))
        assert loaded["eda"]["funnel"]["raw_total"] == 100
        md_text = generate_evaluation_markdown(payload)
        assert "Phân Tích Dữ Liệu Khám Phá (EDA)" in md_text
        assert "Giải Trình Lựa Chọn Đặc Trưng" in md_text

    def test_production_evaluation_report_artifacts_consistent(self):
        assert EVALUATION_JSON_PATH.exists(), "Chưa sinh evaluation_report.json"
        assert EVALUATION_MD_PATH.exists(), "Chưa sinh evaluation_report.md"

        data = json.loads(EVALUATION_JSON_PATH.read_text(encoding="utf-8"))
        assert data["eda"]["funnel"]["clean_total"] == 9693
        blend_metrics = data["model_evaluation"]["model_comparison"]["Ensemble Blend (LGBM + XGB)"]
        assert blend_metrics["r2_vnd"] >= 0.65
        assert blend_metrics["r2_log"] >= 0.70
        cov = data["model_evaluation"]["conformal_diagnostics"]["empirical_coverage_pct"]
        assert 78.0 <= cov <= 86.0
