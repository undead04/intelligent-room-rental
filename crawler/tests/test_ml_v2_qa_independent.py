"""
tests/test_ml_v2_qa_independent.py
Bộ kiểm thử hộp đen độc lập (Independent Black-box QA Test Suite)
cho Tính năng Nâng cấp Mô hình Định giá ML v2 (FEAT-ML-PRICE-MODEL-V2).

Tuân thủ nghiêm ngặt chuẩn mực kiểm thử phần mềm dự án Homigo:
1. Nhóm 1 — Happy Path: Thẩm định giá 5 loại phòng tại 4 đô thị lớn trên toàn quốc.
2. Nhóm 2 — Boundary & Edge Cases: Bản ghi rỗng, thiếu trường, tọa độ ngoài lãnh thổ, đơn giá & diện tích biên.
3. Nhóm 3 — State Mutation & Anti-Leakage: Tính bất biến (Immutability) và chống rò rỉ dữ liệu SpatialTE.transform_train.
4. Nhóm 4 — Persistence & DB Consistency: Nạp artifacts .joblib và kiểm tra tính nhất quán với PostgreSQL.
"""

from __future__ import annotations
import copy
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from crawler.config.paths import (
    ML_ARTIFACTS_DIR,
)

RENT_PIPELINE_PATH = ML_ARTIFACTS_DIR / "rent_pipeline.joblib"
GUARD_PATH = ML_ARTIFACTS_DIR / "guard.joblib"
TRAINING_METRICS_PATH = ML_ARTIFACTS_DIR / "training_metrics.json"
from crawler.model.ml.feature_extractor import (
    ALL_BINARY_KEYS,
    PRUNED_19_FEATURES,
    ROOM_TYPE_FILTER_RULES,
    VIETNAM_LAT_RANGE,
    VIETNAM_LNG_RANGE,
    extract_features_from_record,
)
from crawler.model.ml.models import (
    InputGuard,
    MondrianPriceInterval,
    SpatialTE,
    make_base_features,
)
from crawler.model.ml.price_evaluator import PriceEvaluator, RoomPriceEvaluator


# ==============================================================================
# NHÓM 1: HAPPY PATH (Luồng chuẩn với dữ liệu hợp lệ)
# ==============================================================================

class TestMLv2HappyPath:
    """Kiểm tra luồng chuẩn thẩm định giá 5 loại phòng trên các đô thị lớn."""

    @pytest.fixture
    def evaluator(self) -> PriceEvaluator:
        return PriceEvaluator()

    @pytest.mark.parametrize(
        "city,lat,lng,room_type,room_type_id,area_m2,price_vnd",
        [
            ("TP.HCM", 10.7725, 106.6980, "ROOM", 1, 22.0, 3_500_000),
            ("Hà Nội", 21.0285, 105.8542, "STUDIO", 2, 32.0, 5_500_000),
            ("Đà Nẵng", 16.0618, 108.2208, "APARTMENT", 3, 65.0, 9_500_000),
            ("TP.HCM", 10.7769, 106.7009, "SLEEPBOX", 4, 30.0, 1_600_000),
            ("Cần Thơ", 10.0342, 105.7876, "WHOLE_HOUSE", 5, 110.0, 11_000_000),
        ],
    )
    def test_evaluate_five_room_types_nationwide(
        self,
        evaluator: PriceEvaluator,
        city: str,
        lat: float,
        lng: float,
        room_type: str,
        room_type_id: int,
        area_m2: float,
        price_vnd: int,
    ):
        """Thẩm định giá 5 loại phòng chuẩn tại TP.HCM, Hà Nội, Đà Nẵng, Cần Thơ."""
        record = {
            "listing_id": f"happy_{city}_{room_type}",
            "title": f"Cho thuê {room_type} tiện nghi tại {city}",
            "lat": lat,
            "lng": lng,
            "area_m2": area_m2,
            "price_vnd": price_vnd,
            "room_type": room_type,
            "room_type_id": room_type_id,
            "furnishing_code": 1,
            "aircon": True,
            "private_wc": True,
            "fridge": True,
            "washing_machine": True,
            "elevator": True,
            "mezzanine": False,
            "window_balcony": True,
            "furniture": True,
            "free_hours": True,
            "guard": True,
            "amenity_overall": 0.85,
            "safety_score": 0.80,
        }

        res = evaluator.evaluate_single(record)

        assert res["listing_id"] == f"happy_{city}_{room_type}"
        assert res["guard_status"] == "ok", f"Guard status phải là 'ok' cho phòng hợp lệ tại {city}"
        assert 0.0 <= res["price_score"] <= 1.0, f"price_score phải nằm trong [0.0, 1.0]: {res['price_score']}"
        assert 0.0 <= res["price_score_100"] <= 100.0
        assert res["price_low"] <= res["price_mid"] <= res["price_high"], "Thứ tự khoảng giá không hợp lệ"
        assert res["verdict"] in [
            "Rất rẻ so với thị trường",
            "Rẻ hơn thị trường",
            "Hợp lý",
            "Đắt hơn thị trường",
            "Rất đắt so với thị trường",
        ]

    def test_features_in_contract_19_features(self, evaluator: PriceEvaluator):
        """Kiểm tra hợp đồng 19 features trong pipeline artifact."""
        assert len(evaluator.features_in) == 19
        assert set(evaluator.features_in) == set(PRUNED_19_FEATURES)


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES (Trường hợp biên & dữ liệu dị thường)
# ==============================================================================

class TestMLv2EdgeCases:
    """Kiểm tra khả năng chịu lỗi và xử lý các kịch bản biên bất thường."""

    @pytest.fixture
    def evaluator(self) -> PriceEvaluator:
        return PriceEvaluator()

    def test_empty_batch_and_empty_single_graceful(self, evaluator: PriceEvaluator):
        """Kiểm tra batch rỗng và record rỗng không làm sập (crash) hệ thống."""
        assert evaluator.evaluate_batch([]).empty

        # Bản ghi rỗng không có keys
        res_empty = evaluator.evaluate_single({})
        assert isinstance(res_empty, dict)
        if res_empty:
            assert "price_score" in res_empty

    def test_missing_features_fallback(self, evaluator: PriceEvaluator):
        """Bản ghi thiếu toàn bộ cờ tiện ích và chỉ có giá, diện tích, tọa độ."""
        record = {
            "listing_id": "missing_features_1",
            "price_vnd": 3_000_000,
            "area_m2": 20.0,
            "lat": 10.772,
            "lng": 106.657,
        }
        res = evaluator.evaluate_single(record)
        assert res["guard_status"] == "ok"
        assert 0.0 <= res["price_score"] <= 1.0

    @pytest.mark.parametrize(
        "loc_name,lat,lng",
        [
            ("Singapore", 1.3521, 103.8198),
            ("Tokyo", 35.6762, 139.6503),
            ("Greenwich", 51.48, 0.0),
            ("Null Island", 0.0, 0.0),
            ("Cực Nam ngoài biển", 5.0, 105.0),
            ("Cực Bắc ngoài biên", 25.0, 105.0),
        ],
    )
    def test_out_of_vietnam_coordinates_tagged_as_oor(
        self, evaluator: PriceEvaluator, loc_name: str, lat: float, lng: float
    ):
        """Tọa độ nằm ngoài lãnh thổ Việt Nam bắt buộc phải bị gắn cờ 'oor'."""
        record = {
            "listing_id": f"oor_{loc_name}",
            "price_vnd": 3_000_000,
            "area_m2": 25.0,
            "lat": lat,
            "lng": lng,
            "room_type_id": 1,
        }
        res = evaluator.evaluate_single(record)
        assert res["guard_status"] == "oor", f"Tọa độ tại {loc_name} ({lat}, {lng}) phải bị gắn cờ 'oor'"

    def test_adaptive_ppm_and_price_boundaries_per_room_type(self, evaluator: PriceEvaluator):
        """
        Kiểm tra ngưỡng đơn giá (ppm) và diện tích/giá biên theo từng loại phòng:
        - SLEEPBOX: diện tích 80m2 (ở ghép KTX), giá 600k (ppm = 7.5k >= 5k) -> 'ok'
        - ROOM: diện tích 80m2, giá 600k (ppm = 7.5k < 12k) -> 'odd'
        - SLEEPBOX: diện tích biên 3.0m2 -> 'ok', diện tích 2.5m2 -> 'oor'
        - WHOLE_HOUSE: diện tích biên 250.0m2, giá 30tr -> 'ok', diện tích 260m2 -> 'oor'
        - ROOM: giá 20tr (> 15tr) -> 'oor'
        """
        records = [
            # 0: SLEEPBOX KTX ở ghép diện tích rộng 80m2 giá 600k (ppm = 7.500)
            {"listing_id": "sb_dorm", "price_vnd": 600_000, "area_m2": 80.0, "lat": 10.77, "lng": 106.69, "room_type_id": 4},
            # 1: ROOM thường diện tích 80m2 giá 600k (ppm = 7.500 < 12.000)
            {"listing_id": "rm_odd", "price_vnd": 600_000, "area_m2": 80.0, "lat": 10.77, "lng": 106.69, "room_type_id": 1},
            # 2: SLEEPBOX diện tích biên tối thiểu 3.0m2 giá 1tr2
            {"listing_id": "sb_min_area", "price_vnd": 1_200_000, "area_m2": 3.0, "lat": 10.77, "lng": 106.69, "room_type_id": 4},
            # 3: SLEEPBOX diện tích dưới ngưỡng 2.5m2 (< 3.0)
            {"listing_id": "sb_below_min", "price_vnd": 1_200_000, "area_m2": 2.5, "lat": 10.77, "lng": 106.69, "room_type_id": 4},
            # 4: WHOLE_HOUSE diện tích biên 250m2 giá 30tr
            {"listing_id": "wh_boundary", "price_vnd": 30_000_000, "area_m2": 250.0, "lat": 10.77, "lng": 106.69, "room_type_id": 5},
            # 5: WHOLE_HOUSE diện tích vượt ngưỡng 260m2 (> 250m2)
            {"listing_id": "wh_over_area", "price_vnd": 30_000_000, "area_m2": 260.0, "lat": 10.77, "lng": 106.69, "room_type_id": 5},
            # 6: ROOM giá vượt ngưỡng 20tr (> 15tr)
            {"listing_id": "rm_over_price", "price_vnd": 20_000_000, "area_m2": 30.0, "lat": 10.77, "lng": 106.69, "room_type_id": 1},
        ]

        df_res = evaluator.evaluate_batch(records)
        statuses = dict(zip(df_res["listing_id"], df_res["guard_status"]))

        assert statuses["sb_dorm"] == "ok"
        assert statuses["rm_odd"] == "odd"
        assert statuses["sb_min_area"] == "ok"
        assert statuses["sb_below_min"] == "oor"
        assert statuses["wh_boundary"] == "ok"
        assert statuses["wh_over_area"] == "oor"
        assert statuses["rm_over_price"] == "oor"

    def test_verdict_discrimination_on_extreme_prices(self, evaluator: PriceEvaluator):
        """Phân định rõ rệt giữa phòng siêu rẻ (hời) và phòng siêu đắt."""
        # Phòng Studio trung tâm Q1 full đồ giá chỉ 1.3 triệu -> Cực rẻ
        cheap_rec = {
            "listing_id": "extremely_cheap",
            "price_vnd": 1_300_000,
            "area_m2": 35.0,
            "lat": 10.772,
            "lng": 106.698,
            "room_type_id": 2,
            "furnishing_code": 1,
            "aircon": True,
            "private_wc": True,
            "elevator": True,
            "amenity_overall": 0.95,
        }
        res_cheap = evaluator.evaluate_single(cheap_rec)
        assert res_cheap["z_score"] < -1.0
        assert res_cheap["price_score"] >= 0.75
        assert "rẻ" in res_cheap["verdict"].lower()

        # Phòng trọ thường 10m2 trống trơn giá 14 triệu -> Cực đắt
        expensive_rec = {
            "listing_id": "extremely_expensive",
            "price_vnd": 14_000_000,
            "area_m2": 10.0,
            "lat": 10.850,
            "lng": 106.750,
            "room_type_id": 1,
            "furnishing_code": 2,
            "amenity_overall": 0.1,
        }
        res_expensive = evaluator.evaluate_single(expensive_rec)
        assert res_expensive["z_score"] > 1.0
        assert res_expensive["price_score"] <= 0.25
        assert "đắt" in res_expensive["verdict"].lower()


# ==============================================================================
# NHÓM 3: STATE MUTATION & ANTI-DATA-LEAKAGE
# ==============================================================================

class TestMLv2MutationAndLeakage:
    """Kiểm tra tính bất biến của dữ liệu và chống rò rỉ target trong SpatialTE."""

    def test_immutability_input_record(self):
        """Hàm evaluate_single và evaluate_batch không được làm thay đổi dictionary gốc."""
        evaluator = PriceEvaluator()
        record = {
            "listing_id": "immutability_test",
            "price_vnd": 3_500_000,
            "area_m2": 25.0,
            "lat": 10.772,
            "lng": 106.657,
            "room_type_id": 1,
            "concept_scores": {"private_wc": 1.0, "aircon": 1.0},
        }
        record_copy = copy.deepcopy(record)

        _ = evaluator.evaluate_single(record)
        assert record == record_copy, "evaluate_single đã làm mutate record đầu vào!"

        _ = evaluator.evaluate_batch([record])
        assert record == record_copy, "evaluate_batch đã làm mutate record đầu vào!"

    def test_immutability_make_base_features(self):
        """make_base_features không được mutate DataFrame ban đầu."""
        df_orig = pd.DataFrame({
            "area_m2": [20.0, 30.0],
            "lat": [10.7, 10.8],
            "lng": [106.6, 106.7],
            "amenity_overall": [0.8, 0.9],
        })
        cols_before = list(df_orig.columns)
        vals_before = df_orig.to_numpy().copy()

        out = make_base_features(df_orig)
        assert list(df_orig.columns) == cols_before
        np.testing.assert_array_equal(df_orig.to_numpy(), vals_before)
        assert "amenity_density" in out.columns

    def test_spatial_te_transform_train_strict_anti_leakage(self):
        """
        Stress test chống rò rỉ dữ liệu (Anti-Leakage Red Team Test):
        Tạo 8 điểm tại cùng một tọa độ (hoặc rất gần nhau):
        - Dòng 0: Giá dị biệt cực đại = 50.000.000.000 VNĐ (50 tỷ)
        - Dòng 1..7: Giá thị trường bình thường = 3.000.000 VNĐ
        
        Khi fit SpatialTE và gọi transform_train(X):
        - Dòng 0 PHẢI tính trung bình từ 5 láng giềng khác (đều có giá 3 triệu).
        - Tuyệt đối KHÔNG được chứa giá 50 tỷ của chính nó!
        - Do đó nb5_logy_mean của dòng 0 phải chính xác bằng log1p(3_000_000.0).
        
        Khi gọi transform(X) (cho test query tại cùng tọa độ):
        - Điểm test sẽ tìm thấy láng giềng chứa cả điểm 50 tỷ, do đó giá trị
          sẽ lớn hơn đáng kể so với transform_train.
        """
        n_points = 8
        coords_lat = [10.7700 + i * 1e-5 for i in range(n_points)]
        coords_lng = [106.6500 + i * 1e-5 for i in range(n_points)]

        X = pd.DataFrame({
            "lat": coords_lat,
            "lng": coords_lng,
            "area_m2": [25.0] * n_points,
        })
        # Dòng 0 dị biệt 50 tỷ, các dòng còn lại 3 triệu
        y = pd.Series([50_000_000_000.0] + [3_000_000.0] * (n_points - 1))

        te = SpatialTE(ks=(5,)).fit(X, y)
        tr_train = te.transform_train(X)

        expected_logy = np.log1p(3_000_000.0)
        actual_logy_row0 = tr_train["nb5_logy_mean"].iloc[0]

        # Kiểm tra tính bất nhiễm rò rỉ
        assert np.isclose(actual_logy_row0, expected_logy, atol=1e-4), (
            f"Phát hiện rò rỉ dữ liệu trong transform_train! "
            f"Kỳ vọng {expected_logy:.4f}, thực tế {actual_logy_row0:.4f}"
        )

        # Kiểm tra so với transform inference thông thường
        tr_infer = te.transform(X.iloc[[0]])
        assert tr_infer["nb5_logy_mean"].iloc[0] > actual_logy_row0, (
            "transform thông thường phải bao gồm điểm 50 tỷ của tập fit"
        )


# ==============================================================================
# NHÓM 4: PERSISTENCE & POSTGRESQL CONSISTENCY TEST
# ==============================================================================

class TestMLv2PersistenceAndDatabaseConsistency:
    """Kiểm tra tính nhất quán giữa Artifacts ML và Database PostgreSQL."""

    def test_artifacts_exist_and_metrics_satisfy_spec(self):
        """Kiểm tra các file artifacts tồn tại và chỉ số đạt chuẩn theo SPEC."""
        assert RENT_PIPELINE_PATH.exists(), f"Thiếu {RENT_PIPELINE_PATH}"
        assert GUARD_PATH.exists(), f"Thiếu {GUARD_PATH}"
        assert TRAINING_METRICS_PATH.exists(), f"Thiếu {TRAINING_METRICS_PATH}"

        with open(TRAINING_METRICS_PATH, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        assert metrics["dataset_size"] >= 9000, f"Quy mô dataset phải >= 9000: {metrics['dataset_size']}"
        assert metrics["r2_score"] >= 0.65, f"R2 score phải >= 0.65: {metrics['r2_score']}"
        assert metrics["r2_log_score"] >= 0.70, f"R2 log score phải >= 0.70: {metrics['r2_log_score']}"
        assert 0.78 <= metrics["conformal_coverage"] <= 0.85, (
            f"Coverage phải trong [0.78, 0.85]: {metrics['conformal_coverage']}"
        )
        assert len(metrics["features"]) == 19

    def test_postgresql_listings_price_score_consistency(self):
        """
        Kiểm tra toàn bộ bản ghi trong bảng listings của PostgreSQL:
        1. 100% bản ghi có price_score (count(price_score) == count(*)).
        2. Tất cả giá trị price_score nằm trong [0.0, 1.0].
        3. Phân vị trung bình price_score cân bằng trong khoảng [0.4, 0.6].
        4. Lấy mẫu 5 tin đăng thực tế tính lại bằng PriceEvaluator để đối chiếu.
        """
        from crawler.etl.db_models import create_db_session

        engine, session = create_db_session()
        try:
            with engine.connect() as conn:
                # 1. Thống kê tổng quan cột price_score
                stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(price_score) as scored_count,
                        MIN(price_score) as min_score,
                        MAX(price_score) as max_score,
                        AVG(price_score) as avg_score
                    FROM listings
                """)).mappings().fetchone()

                assert stats["total_count"] > 0, "Bảng listings không được rỗng"
                assert stats["total_count"] == stats["scored_count"], (
                    f"Có bản ghi thiếu price_score: total={stats['total_count']}, scored={stats['scored_count']}"
                )
                assert stats["min_score"] >= 0.0, f"min_score âm: {stats['min_score']}"
                assert stats["max_score"] <= 1.0, f"max_score vượt 1.0: {stats['max_score']}"
                assert 0.40 <= stats["avg_score"] <= 0.60, f"avg_score lệch phân phối: {stats['avg_score']}"

                # 2. Lấy mẫu 5 tin đăng thực tế để thẩm định lại
                sample_rows = conn.execute(text("""
                    SELECT 
                        id, price_vnd, area_m2, lat, lng, room_type_id, 
                        furnishing_code, amenity_overall, safety_score, 
                        concept_scores, price_score
                    FROM listings
                    WHERE price_score IS NOT NULL
                    LIMIT 5
                """)).mappings().fetchall()

                evaluator = PriceEvaluator()
                for r in sample_rows:
                    rec = dict(r)
                    calc_res = evaluator.evaluate_single(rec)
                    stored_score = float(rec["price_score"])
                    calc_score = float(calc_res["price_score"])
                    # Sai số cho phép do làm tròn không vượt quá 0.05
                    assert abs(calc_score - stored_score) <= 0.05, (
                        f"Sai lệch price_score cho listing {rec['id']}: "
                        f"DB={stored_score}, Calc={calc_score}"
                    )
        finally:
            session.close()
            engine.dispose()
