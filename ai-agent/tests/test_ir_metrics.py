"""Bộ kiểm thử Black-box độc lập cho IR Metrics và Benchmark Queries (MỐC 1).

Đặc tả: docs/features/ai-agent-recommendation-eval.md
Module kiểm thử:
- ai-agent/eval/datasets/recommendation_benchmark.py
- ai-agent/eval/ir_metrics.py

Bao gồm 4 nhóm kiểm thử:
1. Nhóm 1: Happy Path (Phòng lý tưởng thỏa mãn 100%, tương thích Dict & RoomItem Pydantic Model)
2. Nhóm 2: Boundary & Edge Cases (Danh sách rỗng, k <= 0, k > len, thiếu toạ độ/diện tích/giá, budget tolerance)
3. Nhóm 3: Ranking Quality, Inversion & Immutability (Độ nhạy thứ tự xếp hạng của nDCG, Reciprocal Rank, không làm biến đổi rooms)
4. Nhóm 4: Constraint Failures & Summarize Breakdown (Vi phạm từng ràng buộc cứng/mềm, tổng hợp IR metrics theo nhóm)
"""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from domain.enums import RoomType
from domain.schemas import RoomItem
from eval.datasets.recommendation_benchmark import (
    BENCHMARK_QUERIES,
    BenchmarkQuery,
    GroundTruthExpectation,
)
from eval.ir_metrics import (
    constraint_satisfaction_breakdown,
    evaluate_room_satisfaction,
    ndcg_at_k,
    precision_at_k,
    reciprocal_rank,
    summarize_queries_ir_metrics,
)


# ==============================================================================
# PHẦN A: KIỂM TRA BỘ DỮ LIỆU KIỂM CHUẨN BENCHMARK_QUERIES
# ==============================================================================

class TestBenchmarkDatasetIntegrity:
    """Kiểm tra tính toàn vẹn và độ phủ của bộ 40 Benchmark Queries."""

    EXPECTED_GROUPS = {
        "G1_BUDGET",
        "G2_SAFETY_AMENITY",
        "G3_GROUP_FRIENDS",
        "G4_PREMIUM_STUDIO",
        "G5_EDGE_CASES",
    }

    def test_total_queries_count_and_distribution(self):
        """Khẳng định tổng cộng đúng 40 câu truy vấn, chia đều 5 nhóm (mỗi nhóm đúng 8 câu)."""
        assert len(BENCHMARK_QUERIES) == 40, f"Kỳ vọng 40 queries, thực tế có {len(BENCHMARK_QUERIES)}"

        actual_groups = {q.group for q in BENCHMARK_QUERIES}
        assert actual_groups == self.EXPECTED_GROUPS, f"Các nhóm không khớp: {actual_groups}"

        for group_name in self.EXPECTED_GROUPS:
            group_queries = [q for q in BENCHMARK_QUERIES if q.group == group_name]
            assert len(group_queries) == 8, (
                f"Nhóm {group_name} phải có đúng 8 câu hỏi, nhưng có {len(group_queries)}"
            )

    def test_unique_ids_and_non_empty_content(self):
        """Khẳng định mọi ID không bị trùng lặp và nội dung câu hỏi/mô tả không rỗng."""
        ids = [q.id for q in BENCHMARK_QUERIES]
        assert len(ids) == len(set(ids)), f"Có ID trùng lặp trong tập benchmark: {ids}"

        for q in BENCHMARK_QUERIES:
            assert q.id.strip(), "ID không được rỗng"
            assert q.query.strip(), f"Nội dung truy vấn của {q.id} không được rỗng"
            assert q.persona_description.strip(), f"Mô tả persona của {q.id} không được rỗng"
            assert isinstance(q.expectation, GroundTruthExpectation)

    def test_valid_geo_coordinates_and_budgets(self):
        """Khẳng định tọa độ TP.HCM và ngân sách trong expectation hợp lệ về mặt địa lý/kinh tế."""
        for q in BENCHMARK_QUERIES:
            exp = q.expectation

            # Toạ độ TP.HCM và vùng giáp ranh (Bình Dương, Thủ Đức)
            if exp.target_lat is not None and exp.target_lng is not None:
                assert 10.5 <= exp.target_lat <= 11.2, f"{q.id}: Vĩ độ lat {exp.target_lat} nằm ngoài TP.HCM"
                assert 106.4 <= exp.target_lng <= 107.0, f"{q.id}: Kinh độ lng {exp.target_lng} nằm ngoài TP.HCM"
                assert exp.max_distance_km is not None and exp.max_distance_km > 0.0

            # Ngân sách (VNĐ)
            if exp.max_budget is not None:
                assert exp.max_budget >= 1_000_000.0, f"{q.id}: max_budget {exp.max_budget} quá thấp"
            if exp.min_budget is not None:
                assert exp.min_budget >= 500_000.0, f"{q.id}: min_budget {exp.min_budget} không hợp lệ"
            if exp.min_budget is not None and exp.max_budget is not None:
                assert exp.min_budget <= exp.max_budget, (
                    f"{q.id}: min_budget ({exp.min_budget}) lớn hơn max_budget ({exp.max_budget})"
                )

            # Ràng buộc loại phòng không được mâu thuẫn trực tiếp (vừa bắt buộc vừa cấm)
            if exp.allowed_room_types and exp.forbidden_room_types:
                overlap = set(exp.allowed_room_types) & set(exp.forbidden_room_types)
                assert not overlap, f"{q.id}: Xung đột allowed và forbidden: {overlap}"


# ==============================================================================
# NHÓM 1: HAPPY PATH (Tương thích Dict & Pydantic RoomItem)
# ==============================================================================

class TestIRMetricsHappyPath:
    """Kiểm thử trường hợp lý tưởng: Phòng đề xuất thỏa mãn 100% kỳ vọng."""

    @pytest.fixture
    def ideal_expectation(self) -> GroundTruthExpectation:
        return GroundTruthExpectation(
            min_budget=1_500_000.0,
            max_budget=2_500_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.0,
            required_amenities=["aircon", "private_wc"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            min_area_m2=15.0,
        )

    def test_happy_path_with_dict_rooms(self, ideal_expectation: GroundTruthExpectation):
        """5 phòng dạng Dict hoàn toàn thỏa mãn -> P@3=1.0, P@5=1.0, RR=1.0, nDCG=1.0, CSR=1.0."""
        rooms_dict = [
            {
                "id": f"room_{i}",
                "title": f"Phòng trọ có máy lạnh wc riêng khép kín số {i}",
                "priceNum": 2_000_000.0,
                "lat": 10.8710,  # Cách ~0.15km
                "lng": 106.8035,
                "area_m2": 20.0,
                "room_type": "ROOM",
                "tags": ["máy lạnh", "wc riêng"],
                "concept_scores": {"aircon": 0.95, "private_wc": 0.90},
            }
            for i in range(1, 6)
        ]

        # Kiểm tra từng phòng
        for r in rooms_dict:
            sat = evaluate_room_satisfaction(r, ideal_expectation)
            assert sat["price_ok"] is True
            assert sat["distance_ok"] is True
            assert sat["room_type_ok"] is True
            assert sat["area_ok"] is True
            assert sat["amenities_ok"] is True
            assert sat["is_fully_satisfied"] is True
            assert sat["relevance_level"] == 3

        # Đo đạc IR Metrics
        p3 = precision_at_k(rooms_dict, ideal_expectation, k=3)
        p5 = precision_at_k(rooms_dict, ideal_expectation, k=5)
        rr = reciprocal_rank(rooms_dict, ideal_expectation)
        ndcg = ndcg_at_k(rooms_dict, ideal_expectation, k=5)
        breakdown = constraint_satisfaction_breakdown(rooms_dict, ideal_expectation)

        assert p3 == 1.0
        assert p5 == 1.0
        assert rr == 1.0
        assert ndcg == 1.0
        assert breakdown["overall_csr"] == 1.0
        assert breakdown["price_compliance_pct"] == 1.0
        assert breakdown["distance_compliance_pct"] == 1.0
        assert breakdown["room_type_compliance_pct"] == 1.0
        assert breakdown["area_compliance_pct"] == 1.0
        assert breakdown["amenities_compliance_pct"] == 1.0

    def test_happy_path_with_pydantic_room_item(self, ideal_expectation: GroundTruthExpectation):
        """Tương thích hoàn hảo với đối tượng Pydantic RoomItem thực tế của hệ thống."""
        pydantic_rooms = [
            RoomItem(
                id=f"room_model_{i}",
                rank=i,
                title=f"Phòng trọ cao cấp có máy lạnh vệ sinh riêng số {i}",
                price="2.2 triệu/tháng",
                priceNum=2_200_000.0,
                lat=10.8720,
                lng=106.8020,
                area_m2=18.0,
                room_type=RoomType.ROOM,
                tags=["máy lạnh", "wc riêng"],
                inferred_tags=[],
                concept_scores={"aircon": 0.88, "private_wc": 0.92},
            )
            for i in range(1, 6)
        ]

        sat = evaluate_room_satisfaction(pydantic_rooms[0], ideal_expectation)
        assert sat["is_fully_satisfied"] is True
        assert sat["relevance_level"] == 3

        p3 = precision_at_k(pydantic_rooms, ideal_expectation, k=3)
        p5 = precision_at_k(pydantic_rooms, ideal_expectation, k=5)
        rr = reciprocal_rank(pydantic_rooms, ideal_expectation)
        ndcg = ndcg_at_k(pydantic_rooms, ideal_expectation, k=5)
        breakdown = constraint_satisfaction_breakdown(pydantic_rooms, ideal_expectation)

        assert p3 == 1.0
        assert p5 == 1.0
        assert rr == 1.0
        assert ndcg == 1.0
        assert breakdown["overall_csr"] == 1.0


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================

class TestIRMetricsBoundaryAndEdgeCases:
    """Kiểm thử giá trị biên, danh sách rỗng, dữ liệu thiếu/lỗi và dung sai ngân sách."""

    @pytest.fixture
    def sample_expectation(self) -> GroundTruthExpectation:
        return GroundTruthExpectation(
            min_budget=2_000_000.0,
            max_budget=4_000_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=2.5,
            min_area_m2=20.0,
            allowed_room_types=["ROOM", "STUDIO"],
        )

    def test_empty_rooms_list_safety(self, sample_expectation: GroundTruthExpectation):
        """Danh sách phòng rỗng [] không được gây lỗi và trả về 0.0 an toàn."""
        empty_rooms: list[dict[str, Any]] = []

        assert precision_at_k(empty_rooms, sample_expectation, k=3) == 0.0
        assert precision_at_k(empty_rooms, sample_expectation, k=5) == 0.0
        assert reciprocal_rank(empty_rooms, sample_expectation) == 0.0
        assert ndcg_at_k(empty_rooms, sample_expectation, k=5) == 0.0

        breakdown = constraint_satisfaction_breakdown(empty_rooms, sample_expectation)
        assert breakdown["overall_csr"] == 0.0
        assert breakdown["price_compliance_pct"] == 0.0
        assert breakdown["distance_compliance_pct"] == 0.0

        summary = summarize_queries_ir_metrics([])
        assert summary["total_queries"] == 0
        assert summary["mean_precision_at_5"] == 0.0
        assert summary["mrr"] == 0.0

    def test_boundary_k_values(self, sample_expectation: GroundTruthExpectation):
        """Kiểm tra k <= 0 hoặc k lớn hơn số lượng phòng trong danh sách."""
        single_satisfied_room = [
            {
                "id": "r1",
                "title": "Phòng đẹp Bách Khoa",
                "priceNum": 3_000_000.0,
                "lat": 10.7730,
                "lng": 106.6580,
                "area_m2": 25.0,
                "room_type": "ROOM",
            }
        ]

        # k <= 0
        assert precision_at_k(single_satisfied_room, sample_expectation, k=0) == 0.0
        assert precision_at_k(single_satisfied_room, sample_expectation, k=-2) == 0.0
        assert ndcg_at_k(single_satisfied_room, sample_expectation, k=0) == 0.0
        assert ndcg_at_k(single_satisfied_room, sample_expectation, k=-1) == 0.0

        # k > len(rooms): 1 phòng đạt trong top k=5 -> P@5 = 1/5 = 0.2
        assert precision_at_k(single_satisfied_room, sample_expectation, k=5) == 0.2
        # ndcg với 1 phòng đạt lý tưởng -> ndcg = 1.0 (vì dcg == idcg)
        assert ndcg_at_k(single_satisfied_room, sample_expectation, k=5) == 1.0

    def test_missing_or_corrupt_room_attributes(self, sample_expectation: GroundTruthExpectation):
        """Phòng thiếu lat/lng, thiếu area_m2, giá 0 hoặc parse lỗi không được gây crash."""
        broken_rooms = [
            {"id": "b1", "priceNum": 0.0, "lat": 10.7725, "lng": 106.6578, "area_m2": 25.0, "room_type": "ROOM"},
            {"id": "b2", "priceNum": 3_000_000.0, "lat": None, "lng": 106.6578, "area_m2": 25.0, "room_type": "ROOM"},
            {"id": "b3", "priceNum": 3_000_000.0, "lat": 10.7725, "lng": None, "area_m2": 25.0, "room_type": "ROOM"},
            {"id": "b4", "priceNum": 3_000_000.0, "lat": 10.7725, "lng": 106.6578, "area_m2": None, "room_type": "ROOM"},
            {"id": "b5", "priceNum": "khong_phai_so", "lat": "loi_lat", "lng": "loi_lng", "area_m2": "loi"},
        ]

        # b1: giá 0 -> price_ok = False
        sat1 = evaluate_room_satisfaction(broken_rooms[0], sample_expectation)
        assert sat1["price_ok"] is False
        assert sat1["is_fully_satisfied"] is False

        # b2 & b3: thiếu lat/lng -> distance_ok = False
        sat2 = evaluate_room_satisfaction(broken_rooms[1], sample_expectation)
        assert sat2["distance_ok"] is False
        assert sat2["distance_km"] is None

        sat3 = evaluate_room_satisfaction(broken_rooms[2], sample_expectation)
        assert sat3["distance_ok"] is False

        # b4: thiếu area_m2 khi có yêu cầu min_area_m2 -> area_ok = False
        sat4 = evaluate_room_satisfaction(broken_rooms[3], sample_expectation)
        assert sat4["area_ok"] is False

        # b5: chuỗi sai định dạng -> trích xuất giá trị mặc định 0.0/None mà không ném Exception
        sat5 = evaluate_room_satisfaction(broken_rooms[4], sample_expectation)
        assert sat5["price_ok"] is False
        assert sat5["distance_ok"] is False
        assert sat5["area_ok"] is False
        assert sat5["is_fully_satisfied"] is False

    def test_budget_tolerance_pct_flexibility(self):
        """Kiểm tra tham số budget_tolerance_pct nới lỏng ngân sách."""
        exp = GroundTruthExpectation(
            min_budget=2_000_000.0,
            max_budget=3_000_000.0,
        )

        # Trường hợp 1: Vượt max_budget nhẹ (3.06 triệu, vượt 2% so với 3.0 triệu)
        room_slightly_over = {"id": "r_over", "priceNum": 3_060_000.0, "title": "Phòng đẹp"}

        # tolerance 0% -> trượt
        sat_strict = evaluate_room_satisfaction(room_slightly_over, exp, budget_tolerance_pct=0.0)
        assert sat_strict["price_ok"] is False

        # tolerance 5% (max lên 3.15 triệu) -> đạt
        sat_loose = evaluate_room_satisfaction(room_slightly_over, exp, budget_tolerance_pct=0.05)
        assert sat_loose["price_ok"] is True

        # Trường hợp 2: Dưới min_budget nhẹ (1.92 triệu, thấp hơn 4% so với 2.0 triệu)
        room_slightly_under = {"id": "r_under", "priceNum": 1_920_000.0, "title": "Phòng rẻ"}

        sat_under_strict = evaluate_room_satisfaction(room_slightly_under, exp, budget_tolerance_pct=0.0)
        assert sat_under_strict["price_ok"] is False

        sat_under_loose = evaluate_room_satisfaction(room_slightly_under, exp, budget_tolerance_pct=0.05)
        assert sat_under_loose["price_ok"] is True


# ==============================================================================
# NHÓM 3: RANKING QUALITY, INVERSION & IMMUTABILITY
# ==============================================================================

class TestIRMetricsRankingQualityAndImmutability:
    """Kiểm thử tính nhạy cảm xếp hạng của nDCG, Reciprocal Rank và tính bất biến của dữ liệu."""

    @pytest.fixture
    def ranking_expectation(self) -> GroundTruthExpectation:
        return GroundTruthExpectation(
            max_budget=3_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.0,
            required_amenities=["aircon", "private_wc"],
            allowed_room_types=["ROOM"],
        )

    def test_ndcg_ranking_inversion_sensitivity(self, ranking_expectation: GroundTruthExpectation):
        """Khẳng định: List A (phòng tốt nhất ở Rank 1) phải có nDCG cao hơn List B (bị đẩy xuống cuối)."""
        # Phòng hoàn hảo (relevance = 3)
        room_perfect = {
            "id": "perfect",
            "title": "Phòng máy lạnh wc riêng",
            "priceNum": 2_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
            "tags": ["máy lạnh", "wc riêng"],
        }
        # Phòng khá tốt (relevance = 2: thiếu 1 tiện ích nhưng đạt hard constraints)
        room_good = {
            "id": "good",
            "title": "Phòng máy lạnh",
            "priceNum": 2_700_000.0,
            "lat": 10.8720,
            "lng": 106.8031,
            "room_type": "ROOM",
            "tags": ["máy lạnh"],
        }
        # Phòng trung bình (relevance = 1: thiếu toàn bộ tiện ích)
        room_fair = {
            "id": "fair",
            "title": "Phòng trống",
            "priceNum": 2_200_000.0,
            "lat": 10.8730,
            "lng": 106.8031,
            "room_type": "ROOM",
            "tags": [],
        }
        # Phòng trượt hard constraint (relevance = 0: quá xa hoặc quá đắt)
        room_bad_1 = {
            "id": "bad1",
            "title": "Phòng quá đắt",
            "priceNum": 10_000_000.0,
            "lat": 10.8700,
            "lng": 106.8031,
            "room_type": "ROOM",
        }
        room_bad_2 = {
            "id": "bad2",
            "title": "Phòng quá xa",
            "priceNum": 2_000_000.0,
            "lat": 10.7000,
            "lng": 106.6000,
            "room_type": "ROOM",
        }

        # List A: Xếp hạng tối ưu [Perfect (3), Good (2), Fair (1), Bad1 (0), Bad2 (0)]
        list_a = [room_perfect, room_good, room_fair, room_bad_1, room_bad_2]
        # List B: Bị đảo ngược tồi tệ [Bad1 (0), Bad2 (0), Fair (1), Good (2), Perfect (3)]
        list_b = [room_bad_1, room_bad_2, room_fair, room_good, room_perfect]

        ndcg_a = ndcg_at_k(list_a, ranking_expectation, k=5)
        ndcg_b = ndcg_at_k(list_b, ranking_expectation, k=5)

        assert ndcg_a == 1.0, "List xếp hạng lý tưởng phải có nDCG = 1.0"
        assert ndcg_a > ndcg_b, f"nDCG(A)={ndcg_a} phải lớn hơn nDCG(B)={ndcg_b}"
        assert ndcg_b < 0.65, f"List đảo ngược phải có nDCG thấp đáng kể, thực tế: {ndcg_b}"

    def test_reciprocal_rank_positions(self, ranking_expectation: GroundTruthExpectation):
        """Khẳng định: Phòng phù hợp ở Rank 1 cho RR=1.0, ở Rank 3 cho RR=1/3, không có phòng cho RR=0.0."""
        satisfying_room = {
            "id": "sat",
            "title": "Phòng máy lạnh wc riêng chuẩn",
            "priceNum": 2_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
            "tags": ["máy lạnh", "wc riêng"],
        }
        failing_room = {
            "id": "fail",
            "title": "Phòng vi phạm giá",
            "priceNum": 9_000_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
        }

        # Rank 1: RR = 1.0
        list_rank_1 = [satisfying_room, failing_room, failing_room]
        assert reciprocal_rank(list_rank_1, ranking_expectation) == 1.0

        # Rank 3: RR = 1/3 ~ 0.3333
        list_rank_3 = [failing_room, failing_room, satisfying_room]
        rr_3 = reciprocal_rank(list_rank_3, ranking_expectation)
        assert math.isclose(rr_3, 1.0 / 3.0, rel_tol=1e-4)

        # Không có phòng nào đạt: RR = 0.0
        list_no_match = [failing_room, failing_room]
        assert reciprocal_rank(list_no_match, ranking_expectation) == 0.0

    def test_immutability_input_rooms_not_modified(self, ranking_expectation: GroundTruthExpectation):
        """Khẳng định: Các hàm tính IR metrics không được làm thay đổi (mutate) dữ liệu đầu vào."""
        original_rooms = [
            {
                "id": "r1",
                "title": "Phòng trọ Thủ Đức",
                "priceNum": 2_500_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "room_type": "ROOM",
                "tags": ["máy lạnh"],
                "concept_scores": {"aircon": 0.8},
            },
            {
                "id": "r2",
                "title": "Sleepbox KTX",
                "priceNum": 1_500_000.0,
                "lat": 10.8720,
                "lng": 106.8035,
                "room_type": "SLEEPBOX",
                "tags": [],
            },
        ]

        # Tạo bản sao sâu để đối chiếu
        rooms_clone = copy.deepcopy(original_rooms)

        # Thực thi toàn bộ các hàm đo đạc
        _ = precision_at_k(original_rooms, ranking_expectation, k=2)
        _ = reciprocal_rank(original_rooms, ranking_expectation)
        _ = ndcg_at_k(original_rooms, ranking_expectation, k=2)
        _ = constraint_satisfaction_breakdown(original_rooms, ranking_expectation)

        # Khẳng định danh sách rooms hoàn toàn giữ nguyên trạng thái
        assert original_rooms == rooms_clone, "Dữ liệu rooms đã bị thay đổi (mutation) trong quá trình tính toán!"


# ==============================================================================
# NHÓM 4: CONSTRAINT FAILURES & SUMMARIZE BREAKDOWN
# ==============================================================================

class TestIRMetricsConstraintFailuresAndSummary:
    """Kiểm thử vi phạm từng ràng buộc cụ thể và tính năng tổng hợp IR Metrics đa truy vấn."""

    def test_specific_constraint_failures(self):
        """Kiểm tra từng tiêu chí độc lập: vi phạm giá, khoảng cách, loại phòng, diện tích, tiện ích."""
        exp = GroundTruthExpectation(
            min_budget=2_000_000.0,
            max_budget=3_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=2.0,
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            min_area_m2=20.0,
            required_amenities=["aircon", "washing_machine"],
        )

        # 1. Vi phạm Giá (quá cao)
        r_price_fail = {
            "priceNum": 3_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
            "area_m2": 25.0,
            "tags": ["máy lạnh", "máy giặt"],
        }
        res_price = evaluate_room_satisfaction(r_price_fail, exp)
        assert res_price["price_ok"] is False
        assert res_price["is_fully_satisfied"] is False
        assert res_price["relevance_level"] == 0

        # 2. Vi phạm Khoảng cách (xa > 2km, ví dụ ở Q10)
        r_dist_fail = {
            "priceNum": 2_500_000.0,
            "lat": 10.7725,
            "lng": 106.6578,
            "room_type": "ROOM",
            "area_m2": 25.0,
            "tags": ["máy lạnh", "máy giặt"],
        }
        res_dist = evaluate_room_satisfaction(r_dist_fail, exp)
        assert res_dist["distance_ok"] is False
        assert res_dist["distance_km"] > 10.0
        assert res_dist["relevance_level"] == 0

        # 3. Vi phạm Loại phòng cấm (SLEEPBOX)
        r_type_fail = {
            "priceNum": 2_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "SLEEPBOX",
            "area_m2": 25.0,
            "tags": ["máy lạnh", "máy giặt"],
        }
        res_type = evaluate_room_satisfaction(r_type_fail, exp)
        assert res_type["room_type_ok"] is False
        assert res_type["relevance_level"] == 0

        # 4. Vi phạm Diện tích (15m2 < 20m2 yêu cầu)
        r_area_fail = {
            "priceNum": 2_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
            "area_m2": 15.0,
            "tags": ["máy lạnh", "máy giặt"],
        }
        res_area = evaluate_room_satisfaction(r_area_fail, exp)
        assert res_area["area_ok"] is False
        # Hard constraints đều đạt, chỉ thiếu area -> relevance_level = 2 (vì có đủ tiện ích)
        assert res_area["relevance_level"] == 2
        assert res_area["is_fully_satisfied"] is False

        # 5. Vi phạm Tiện ích (thiếu máy giặt)
        r_amenity_fail = {
            "priceNum": 2_500_000.0,
            "lat": 10.8710,
            "lng": 106.8031,
            "room_type": "ROOM",
            "area_m2": 25.0,
            "tags": ["máy lạnh"],  # Thiếu máy giặt
        }
        res_amenity = evaluate_room_satisfaction(r_amenity_fail, exp)
        assert res_amenity["amenities_ok"] is False
        assert "washing_machine" in res_amenity["missing_amenities"]
        assert "aircon" in res_amenity["matched_amenities"]
        assert res_amenity["amenities_matched_ratio"] == 0.5
        assert res_amenity["is_fully_satisfied"] is False

    def test_safe_area_amenity_inference_from_concepts(self):
        """Tiện ích safe_area có thể thỏa mãn nếu có camera, fingerprint_lock hoặc guard."""
        exp = GroundTruthExpectation(required_amenities=["safe_area"])

        # Có khóa vân tay trong concept_scores -> thỏa mãn safe_area
        r_fingerprint = {
            "priceNum": 3_000_000.0,
            "title": "Phòng đẹp",
            "concept_scores": {"fingerprint_lock": 0.85},
        }
        res = evaluate_room_satisfaction(r_fingerprint, exp)
        assert res["amenities_ok"] is True
        assert "safe_area" in res["matched_amenities"]

        # Có camera trong tags -> thỏa mãn safe_area
        r_camera = {
            "priceNum": 3_000_000.0,
            "title": "Phòng an ninh",
            "tags": ["camera an ninh 24/7"],
        }
        res_cam = evaluate_room_satisfaction(r_camera, exp)
        assert res_cam["amenities_ok"] is True

    def test_constraint_satisfaction_breakdown_metrics(self):
        """Kiểm tra tỷ lệ tuân thủ từng tiêu chí trong constraint_satisfaction_breakdown."""
        exp = GroundTruthExpectation(
            max_budget=3_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=2.0,
            allowed_room_types=["ROOM"],
        )

        rooms = [
            # Phòng 1: Đạt tất cả
            {"priceNum": 2_500_000.0, "lat": 10.8710, "lng": 106.8031, "room_type": "ROOM"},
            # Phòng 2: Hỏng giá (quá đắt)
            {"priceNum": 5_000_000.0, "lat": 10.8710, "lng": 106.8031, "room_type": "ROOM"},
            # Phòng 3: Hỏng toạ độ (quá xa)
            {"priceNum": 2_000_000.0, "lat": 10.7000, "lng": 106.6000, "room_type": "ROOM"},
            # Phòng 4: Hỏng loại phòng
            {"priceNum": 2_000_000.0, "lat": 10.8710, "lng": 106.8031, "room_type": "APARTMENT"},
        ]

        breakdown = constraint_satisfaction_breakdown(rooms, exp)

        # 3/4 phòng đạt giá = 0.75
        assert breakdown["price_compliance_pct"] == 0.75
        # 3/4 phòng đạt khoảng cách = 0.75
        assert breakdown["distance_compliance_pct"] == 0.75
        # 3/4 phòng đạt loại phòng = 0.75
        assert breakdown["room_type_compliance_pct"] == 0.75
        # Chỉ 1/4 phòng đạt 100% tất cả tiêu chí = 0.25
        assert breakdown["overall_csr"] == 0.25

    def test_summarize_queries_ir_metrics_by_group_and_aggregation(self):
        """Kiểm tra summarize_queries_ir_metrics gom nhóm chuẩn xác theo Persona."""
        mock_queries_results = [
            # Nhóm G1_BUDGET (2 queries)
            {
                "query_id": "G1_01",
                "group": "G1_BUDGET",
                "precision_at_3": 1.0,
                "precision_at_5": 0.8,
                "reciprocal_rank": 1.0,
                "ndcg_at_5": 0.95,
                "overall_csr": 0.8,
                "breakdown": {
                    "price_compliance_pct": 1.0,
                    "distance_compliance_pct": 1.0,
                    "room_type_compliance_pct": 1.0,
                    "area_compliance_pct": 1.0,
                    "amenities_compliance_pct": 0.8,
                },
            },
            {
                "query_id": "G1_02",
                "group": "G1_BUDGET",
                "precision_at_3": 0.67,
                "precision_at_5": 0.6,
                "reciprocal_rank": 1.0,
                "ndcg_at_5": 0.85,
                "overall_csr": 0.6,
                "breakdown": {
                    "price_compliance_pct": 1.0,
                    "distance_compliance_pct": 0.8,
                    "room_type_compliance_pct": 1.0,
                    "area_compliance_pct": 1.0,
                    "amenities_compliance_pct": 0.8,
                },
            },
            # Nhóm G2_SAFETY_AMENITY (1 query)
            {
                "query_id": "G2_01",
                "group": "G2_SAFETY_AMENITY",
                "precision_at_3": 1.0,
                "precision_at_5": 1.0,
                "reciprocal_rank": 1.0,
                "ndcg_at_5": 1.0,
                "overall_csr": 1.0,
                "breakdown": {
                    "price_compliance_pct": 1.0,
                    "distance_compliance_pct": 1.0,
                    "room_type_compliance_pct": 1.0,
                    "area_compliance_pct": 1.0,
                    "amenities_compliance_pct": 1.0,
                },
            },
        ]

        summary = summarize_queries_ir_metrics(mock_queries_results)

        assert summary["total_queries"] == 3
        # Mean P@5 = (0.8 + 0.6 + 1.0) / 3 = 0.8
        assert math.isclose(summary["mean_precision_at_5"], 0.8, rel_tol=1e-3)
        assert summary["mrr"] == 1.0

        # Kiểm tra by_group
        by_group = summary["by_group"]
        assert "G1_BUDGET" in by_group
        assert "G2_SAFETY_AMENITY" in by_group
        assert by_group["G1_BUDGET"]["count"] == 2
        assert by_group["G2_SAFETY_AMENITY"]["count"] == 1

        # Mean P@5 của G1 = (0.8 + 0.6) / 2 = 0.7
        assert by_group["G1_BUDGET"]["mean_precision_at_5"] == 0.7
        # Mean P@5 của G2 = 1.0
        assert by_group["G2_SAFETY_AMENITY"]["mean_precision_at_5"] == 1.0

    def test_summarize_queries_auto_compute_from_raw_rooms(self):
        """summarize_queries_ir_metrics tự động tính toán từ rooms và expectation nếu chưa có điểm."""
        exp = GroundTruthExpectation(
            max_budget=3_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=2.0,
        )
        rooms = [
            {"priceNum": 2_000_000.0, "lat": 10.8710, "lng": 106.8031},
            {"priceNum": 2_200_000.0, "lat": 10.8720, "lng": 106.8031},
            {"priceNum": 2_500_000.0, "lat": 10.8715, "lng": 106.8031},
        ]

        raw_item = {
            "query_id": "RAW_01",
            "group": "G1_BUDGET",
            "rooms": rooms,
            "expectation": exp,
        }

        summary = summarize_queries_ir_metrics([raw_item])
        assert summary["total_queries"] == 1
        assert summary["mean_precision_at_3"] == 1.0
        assert summary["mrr"] == 1.0
        assert summary["mean_ndcg_at_5"] == 1.0
        assert summary["mean_csr"] == 1.0

    def test_no_shared_landlord_self_managed_equivalence(self):
        """Phòng tòa nhà tự quản (free_hours + fingerprint_lock >= 0.7) thỏa mãn no_shared_landlord."""
        exp = GroundTruthExpectation(required_amenities=["no_shared_landlord"])
        r_ok = {
            "priceNum": 3_500_000.0,
            "concept_scores": {"no_shared_landlord": 0.0, "free_hours": 1.0, "fingerprint_lock": 1.0},
        }
        r_bad = {
            "priceNum": 3_500_000.0,
            "concept_scores": {"no_shared_landlord": 0.0, "free_hours": 1.0, "fingerprint_lock": 0.0},
        }
        assert evaluate_room_satisfaction(r_ok, exp)["amenities_ok"] is True
        assert evaluate_room_satisfaction(r_bad, exp)["amenities_ok"] is False
