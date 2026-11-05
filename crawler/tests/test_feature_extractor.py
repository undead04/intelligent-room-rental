"""
tests/test_feature_extractor.py
Bộ kiểm thử hộp đen nghiêm ngặt (Black-box Testing) cho Feature Extractor v2.

Tuân thủ đầy đủ 4 nhóm test cases bắt buộc:
1. Nhóm 1 (Happy Path): Trích xuất bản ghi hợp lệ ở các tỉnh thành (TP.HCM, Hà Nội, Đà Nẵng, Cần Thơ).
2. Nhóm 2 (Boundary & Edge Cases): Xử lý KTX/Sleepbox/ở ghép, diện tích/giá biên, tọa độ rác, JSON hỏng.
3. Nhóm 3 (State Mutation & Immutability): Tính bất biến của dữ liệu đầu vào khi trích xuất.
4. Nhóm 4 (Persistence & Dataset Integration): Nạp Parquet và kiểm tra tính toàn vẹn của dataset sạch.
"""

import copy
import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from crawler.model.ml.feature_extractor import (
    ALL_BINARY_KEYS,
    CANONICAL_AMENITY_KEYS,
    CANONICAL_RULE_KEYS,
    CANONICAL_SAFETY_KEYS,
    ROOM_TYPE_FILTER_RULES,
    VIETNAM_LAT_RANGE,
    VIETNAM_LNG_RANGE,
    compute_haversine_distance_vectorized,
    compute_single_poi_distance,
    export_records_to_parquet,
    extract_features_from_record,
    filter_valid_dataframe,
    load_and_preprocess_dataset,
    load_poi_locations_from_config,
)


# ==============================================================================
# NHÓM 1: HAPPY PATH (Luồng chuẩn với dữ liệu hợp lệ)
# ==============================================================================

class TestFeatureExtractorHappyPath:
    """Kiểm tra trích xuất đầy đủ và chính xác các đặc trưng từ bản ghi chuẩn."""

    @pytest.mark.parametrize(
        "city_name,lat,lng,expected_hub_max_km",
        [
            ("TP.HCM", 10.7725, 106.6980, 5.0),
            ("Hà Nội", 21.0285, 105.8542, 5.0),
            ("Đà Nẵng", 16.0618, 108.2208, 5.0),
            ("Cần Thơ", 10.0342, 105.7876, 5.0),
            ("Bình Dương", 10.9805, 106.6745, 5.0),
        ],
    )
    def test_extract_record_multi_city(self, city_name, lat, lng, expected_hub_max_km):
        rec = {
            "listing_id": f"test_{city_name}",
            "area_m2": 28.5,
            "price_vnd": 3800000.0,
            "lat": lat,
            "lng": lng,
            "room_type": "STUDIO",
            "room_type_id": 2,
            "furnishing_code": 1.0,
            "concept_scores": {
                "private_wc": 1.0,
                "aircon": 1.0,
                "kitchen": 0.9,
                "washing_machine": 1.0,
                "fridge": 1.0,
                "elevator": 1.0,
                "fingerprint_lock": 1.0,
            },
            "amenity_overall": 0.85,
            "safety_score": 0.70,
        }

        row = extract_features_from_record(rec)

        # 1. Kiểm tra các định danh cơ sở
        assert row["listing_id"] == f"test_{city_name}"
        assert row["area_m2"] == 28.5
        assert row["price_vnd"] == 3800000.0
        assert row["room_type_id"] == 2
        assert row["furnishing_code"] == 1.0

        # 2. Kiểm tra đủ 17 cờ nhị phân
        for k in ALL_BINARY_KEYS:
            assert f"is_{k}" in row
            assert row[f"is_{k}"] in (0, 1)

        assert row["is_private_wc"] == 1
        assert row["is_aircon"] == 1
        assert row["is_fridge"] == 1
        assert row["is_elevator"] == 1
        assert row["is_fingerprint_lock"] == 1

        # 3. Kiểm tra điểm chất lượng ngữ nghĩa
        assert row["amenity_overall"] == 0.85
        assert row["safety_score"] == 0.70

        # 4. Kiểm tra khoảng cách POI đa đô thị
        assert 0.0 <= row["dist_nearest_hub_km"] <= expected_hub_max_km
        assert row["dist_nearest_uni_km"] >= 0.0

    def test_extract_record_fallback_scores_from_binary_flags(self):
        """Khi bản ghi không có sẵn amenity_overall và safety_score, hàm tự nội suy chuẩn."""
        rec = {
            "listing_id": "test_fallback",
            "area_m2": 20.0,
            "price_vnd": 2500000.0,
            "lat": 10.85,
            "lng": 106.77,
            "room_type": "ROOM",
            "report": {
                "amenities": {
                    "private_wc": {"value": "yes"},
                    "aircon": {"value": "yes"},
                },
                "safety": {
                    "camera": {"value": "yes"},
                    "guard": {"value": "yes"},
                },
            },
        }

        row = extract_features_from_record(rec)
        # private_wc (20) + aircon (20) = 40/100 -> 0.40
        assert row["amenity_overall"] == 0.40
        # camera (0.30) + guard (0.30) = 0.60
        assert row["safety_score"] == 0.60


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES (Biên & trường hợp ngoại lai)
# ==============================================================================

class TestFeatureExtractorEdgeCases:
    """Kiểm tra tính chịu lỗi với dữ liệu bất thường, thiếu trường hoặc phân khúc đặc thù."""

    def test_sleepbox_adaptive_filtering_preserves_dorm_records(self):
        """Phân khúc SLEEPBOX (KTX/ở ghép) với diện tích phòng chung lớn giá rẻ không bị lọc nhầm."""
        rows = [
            # 1. KTX phòng sinh hoạt chung 45m2, giá 1.2M/giường (ppm = 26.666 đ/m2)
            {
                "listing_id": "sleepbox_dorm_shared",
                "area_m2": 45.0,
                "price_vnd": 1200000.0,
                "lat": 10.77,
                "lng": 106.69,
                "room_type_id": 4,  # SLEEPBOX
            },
            # 2. Hộp ngủ đơn diện tích 4.5m2, giá 1.5M (ppm = 333.333 đ/m2)
            {
                "listing_id": "sleepbox_single_box",
                "area_m2": 4.5,
                "price_vnd": 1500000.0,
                "lat": 10.78,
                "lng": 106.70,
                "room_type_id": 4,  # SLEEPBOX
            },
            # 3. Tin rác giá 50.000 đ hoặc diện tích 1.0m2 (bị lọc)
            {
                "listing_id": "sleepbox_trash",
                "area_m2": 1.0,
                "price_vnd": 50000.0,
                "lat": 10.77,
                "lng": 106.69,
                "room_type_id": 4,
            },
        ]
        df = pd.DataFrame([extract_features_from_record(r) for r in rows])
        df_clean = filter_valid_dataframe(df)

        kept_ids = df_clean["listing_id"].tolist()
        assert "sleepbox_dorm_shared" in kept_ids
        assert "sleepbox_single_box" in kept_ids
        assert "sleepbox_trash" not in kept_ids

    def test_filter_out_of_vietnam_coordinates(self):
        """Tọa độ ngoài lãnh thổ Việt Nam (0,0 hoặc tọa độ nước ngoài) phải bị loại bỏ."""
        rows = [
            {"listing_id": "ok_hcm", "area_m2": 20.0, "price_vnd": 3000000.0, "lat": 10.77, "lng": 106.69, "room_type_id": 1},
            {"listing_id": "ok_hanoi", "area_m2": 25.0, "price_vnd": 3500000.0, "lat": 21.02, "lng": 105.85, "room_type_id": 1},
            {"listing_id": "err_zero", "area_m2": 20.0, "price_vnd": 3000000.0, "lat": 0.0, "lng": 0.0, "room_type_id": 1},
            {"listing_id": "err_swapped", "area_m2": 20.0, "price_vnd": 3000000.0, "lat": 106.69, "lng": 10.77, "room_type_id": 1},
            {"listing_id": "err_foreign", "area_m2": 20.0, "price_vnd": 3000000.0, "lat": 35.68, "lng": 139.76, "room_type_id": 1},  # Tokyo
        ]
        df = pd.DataFrame([extract_features_from_record(r) for r in rows])
        df_clean = filter_valid_dataframe(df)

        kept_ids = df_clean["listing_id"].tolist()
        assert kept_ids == ["ok_hcm", "ok_hanoi"]

    def test_extract_features_with_corrupted_json_or_none(self):
        """Xử lý an toàn khi report hoặc concept_scores bị None, rỗng hoặc là chuỗi JSON lỗi."""
        corrupted_rec = {
            "listing_id": "corrupted_item",
            "area_m2": None,
            "price_vnd": "not_a_number",
            "lat": None,
            "lng": None,
            "concept_scores": "{ invalid json string",
            "report": "not a json string at all",
            "room_type": None,
            "room_type_id": None,
        }
        # Hàm không được raise exception
        row = extract_features_from_record(corrupted_rec)
        assert row["listing_id"] == "corrupted_item"
        assert row["area_m2"] == 0.0
        assert row["price_vnd"] == 0.0
        assert row["room_type_id"] == 1  # Fallback to ROOM
        assert row["dist_nearest_hub_km"] == 999.0
        assert row["amenity_overall"] == 0.0
        assert row["safety_score"] == 0.0


# ==============================================================================
# NHÓM 3: STATE MUTATION & IMMUTABILITY (Tính bất biến)
# ==============================================================================

class TestFeatureExtractorImmutability:
    """Đảm bảo hàm extract_features_from_record không làm thay đổi đối tượng đầu vào."""

    def test_input_dict_not_mutated(self):
        original = {
            "listing_id": "immutable_test",
            "area_m2": 30.0,
            "price_vnd": 4500000.0,
            "lat": 10.77,
            "lng": 106.69,
            "concept_scores": {"private_wc": 1.0, "aircon": 1.0},
            "report": {"amenities": {"kitchen": {"value": "yes"}}},
        }
        deep_copied = copy.deepcopy(original)

        _ = extract_features_from_record(original)

        assert original == deep_copied, "Hàm extract_features_from_record đã làm thay đổi (mutate) dict đầu vào!"

    def test_deterministic_multiple_calls(self):
        rec = {
            "listing_id": "determ_test",
            "area_m2": 25.0,
            "price_vnd": 3000000.0,
            "lat": 16.06,
            "lng": 108.22,
            "room_type_id": 2,
        }
        res1 = extract_features_from_record(rec)
        res2 = extract_features_from_record(rec)
        assert res1 == res2


# ==============================================================================
# NHÓM 4: PERSISTENCE & DATASET INTEGRATION TEST (Kiểm thử nạp thực tế)
# ==============================================================================

class TestFeatureExtractorPersistenceAndIntegration:
    """Kiểm tra quy trình xuất/đọc file Parquet và nạp toàn bộ dataset."""

    def test_export_and_read_parquet(self):
        records = [
            {
                "listing_id": "pq_1",
                "area_m2": 20.0,
                "price_vnd": 2500000.0,
                "concept_scores": {"private_wc": 1.0},
                "report": {"amenities": {"aircon": {"value": "yes"}}},
            },
            {
                "listing_id": "pq_2",
                "area_m2": 35.0,
                "price_vnd": 5000000.0,
                "concept_scores": {},
                "report": {},
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            exported_path = export_records_to_parquet(records, tmp_path)
            assert exported_path.exists()

            df_read = pd.read_parquet(exported_path)
            assert len(df_read) == 2
            assert "listing_id" in df_read.columns
            assert "concept_scores" in df_read.columns
            # Kiểm tra đọc lại được JSON string
            assert isinstance(df_read["concept_scores"].iloc[0], str)
            parsed_cs = json.loads(df_read["concept_scores"].iloc[0])
            assert parsed_cs.get("private_wc") == 1.0
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_load_poi_locations_from_config_and_fallback(self):
        """Kiểm tra nạp POI từ file config JSON và cơ chế fallback an toàn khi file lỗi hoặc không tồn tại."""
        # 1. Nạp từ file chuẩn
        cities, unis = load_poi_locations_from_config()
        assert len(cities) >= 10
        assert len(unis) >= 10
        assert all(isinstance(c[0], float) and isinstance(c[1], float) for c in cities)

        # 2. Fallback khi file không tồn tại
        cities_fb, unis_fb = load_poi_locations_from_config("non_existent_poi_file.json")
        assert len(cities_fb) >= 10
        assert len(unis_fb) >= 10

        # 3. Fallback khi file JSON rác/lỗi cú pháp
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write("{ invalid json")
            bad_path = Path(tmp.name)
        try:
            cities_bad, unis_bad = load_poi_locations_from_config(bad_path)
            assert len(cities_bad) >= 10
            assert len(unis_bad) >= 10
        finally:
            if bad_path.exists():
                bad_path.unlink()

    def test_load_and_preprocess_dataset_full_dataset(self):
        """Kiểm tra nạp dataset thực tế đạt đủ tiêu chí số lượng bản ghi >= 9.500 và 26 features."""
        X, y = load_and_preprocess_dataset(auto_build_cache=True)

        # 1. Số lượng bản ghi sạch phải đạt >= 9.500
        assert len(X) >= 9500, f"Số lượng bản ghi {len(X)} thấp hơn kỳ vọng 9.500!"
        assert len(y) == len(X)

        # 2. Đầy đủ 26 features
        expected_features = [
            "area_m2",
            "lat",
            "lng",
            "room_type_id",
            "furnishing_code",
            "is_private_wc",
            "is_aircon",
            "is_mezzanine",
            "is_kitchen",
            "is_fridge",
            "is_washing_machine",
            "is_window_balcony",
            "is_furniture",
            "is_parking",
            "is_elevator",
            "is_free_hours",
            "is_no_shared_landlord",
            "is_pet_allowed",
            "is_fingerprint_lock",
            "is_camera",
            "is_guard",
            "is_safe_area",
            "amenity_overall",
            "safety_score",
            "dist_nearest_hub_km",
            "dist_nearest_uni_km",
        ]
        assert X.columns.tolist() == expected_features

        # 3. Toàn bộ 5 loại phòng đều có dữ liệu
        counts = X["room_type_id"].value_counts().to_dict()
        for rt_id in (1, 2, 3, 4, 5):
            assert rt_id in counts, f"Thiếu dữ liệu của room_type_id={rt_id}"
            assert counts[rt_id] > 0

        # 4. Giá thuê hợp lệ và không có giá trị NaN
        assert not X.isna().any().any(), "Tập đặc trưng X có chứa giá trị NaN!"
        assert not y.isna().any(), "Biến mục tiêu y có chứa giá trị NaN!"
        assert (y > 0).all(), "Có bản ghi giá thuê <= 0!"

