"""Bộ kiểm thử Black-box độc lập cho Gemini LLM-as-a-Judge và Runner Đánh giá Gợi ý Phòng trọ (MỐC 2).

Đặc tả kỹ thuật: docs/features/ai-agent-recommendation-eval.md
Module kiểm thử:
- ai-agent/eval/llm_judge.py
- ai-agent/eval/run_recommendation_eval.py

Bao gồm 4 nhóm kiểm thử Black-box độc lập:
1. Nhóm 1 — Schema Validation (Pydantic constraints ge=1.0, le=5.0, auto compute overall_score, missing fields)
2. Nhóm 2 — Offline Rule-based Judge (Model=None: phòng lý tưởng, vi phạm giá/khoảng cách/loại phòng, danh sách rỗng, ảo giác số liệu)
3. Nhóm 3 — Mocked Online LLM Judge (Structured output mock, dict parsing, graceful fallback khi timeout/network exception)
4. Nhóm 4 — Runner Formatting & Reporting (generate_markdown_report, save_evaluation_results, tính toàn vẹn file JSON và Markdown)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from eval.datasets.recommendation_benchmark import GroundTruthExpectation
from eval.llm_judge import (
    RecommendationJudgeReport,
    compute_overall_score,
    evaluate_recommendation_quality,
    get_judge_llm,
    _rule_based_recommendation_judge,
)
from eval.run_recommendation_eval import (
    _build_markdown_report,
    generate_markdown_report,
    save_evaluation_results,
)


# ==============================================================================
# NHÓM 1: SCHEMA VALIDATION (Pydantic constraints & overall_score calculation)
# ==============================================================================


class TestRecommendationJudgeReportSchema:
    """Kiểm thử tính đúng đắn và các ràng buộc schema Pydantic của RecommendationJudgeReport."""

    def test_valid_schema_initialization_full_fields(self):
        """Khởi tạo thành công RecommendationJudgeReport với đầy đủ các trường hợp lệ."""
        report = RecommendationJudgeReport(
            relevance_score=4.5,
            ranking_score=4.0,
            faithfulness_score=5.0,
            overall_score=4.5,
            strengths=["Bắt chính xác ngân sách", "Top 1 tối ưu khoảng cách"],
            weaknesses=["Chưa nêu rõ chi phí điện nước"],
            rationale="Kết quả gợi ý xuất sắc, tuân thủ mọi ràng buộc cứng.",
        )

        assert report.relevance_score == 4.5
        assert report.ranking_score == 4.0
        assert report.faithfulness_score == 5.0
        assert report.overall_score == 4.5
        assert len(report.strengths) == 2
        assert len(report.weaknesses) == 1
        assert "xuất sắc" in report.rationale

    def test_score_range_boundaries_lower_than_minimum(self):
        """Điểm số < 1.0 phải ném lỗi Pydantic ValidationError."""
        # 1. relevance_score < 1.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=0.9,
                ranking_score=4.0,
                faithfulness_score=4.0,
                overall_score=3.0,
                rationale="Điểm relevance quá thấp",
            )
        assert "relevance_score" in str(exc_info.value)

        # 2. ranking_score < 1.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=4.0,
                ranking_score=0.5,
                faithfulness_score=4.0,
                overall_score=3.0,
                rationale="Điểm ranking quá thấp",
            )
        assert "ranking_score" in str(exc_info.value)

        # 3. faithfulness_score < 1.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=4.0,
                ranking_score=4.0,
                faithfulness_score=-0.5,
                overall_score=3.0,
                rationale="Điểm faithfulness âm",
            )
        assert "faithfulness_score" in str(exc_info.value)

        # 4. overall_score < 1.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=1.0,
                ranking_score=1.0,
                faithfulness_score=1.0,
                overall_score=0.0,
                rationale="Điểm overall < 1.0",
            )
        assert "overall_score" in str(exc_info.value)

    def test_score_range_boundaries_higher_than_maximum(self):
        """Điểm số > 5.0 phải ném lỗi Pydantic ValidationError."""
        # 1. relevance_score > 5.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=5.1,
                ranking_score=4.0,
                faithfulness_score=4.0,
                overall_score=4.5,
                rationale="Điểm relevance vượt trần",
            )
        assert "relevance_score" in str(exc_info.value)

        # 2. ranking_score > 5.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=4.0,
                ranking_score=6.0,
                faithfulness_score=4.0,
                overall_score=4.5,
                rationale="Điểm ranking vượt trần",
            )
        assert "ranking_score" in str(exc_info.value)

        # 3. faithfulness_score > 5.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=4.0,
                ranking_score=4.0,
                faithfulness_score=10.0,
                overall_score=4.5,
                rationale="Điểm faithfulness vượt trần",
            )
        assert "faithfulness_score" in str(exc_info.value)

        # 4. overall_score > 5.0
        with pytest.raises(ValidationError) as exc_info:
            RecommendationJudgeReport(
                relevance_score=5.0,
                ranking_score=5.0,
                faithfulness_score=5.0,
                overall_score=5.5,
                rationale="Điểm overall vượt trần",
            )
        assert "overall_score" in str(exc_info.value)

    def test_valid_exact_boundary_values_1_and_5(self):
        """Giá trị biên chính xác 1.0 và 5.0 phải hợp lệ."""
        report_min = RecommendationJudgeReport(
            relevance_score=1.0,
            ranking_score=1.0,
            faithfulness_score=1.0,
            overall_score=1.0,
            rationale="Mức điểm tối thiểu",
        )
        assert report_min.relevance_score == 1.0
        assert report_min.overall_score == 1.0

        report_max = RecommendationJudgeReport(
            relevance_score=5.0,
            ranking_score=5.0,
            faithfulness_score=5.0,
            overall_score=5.0,
            rationale="Mức điểm tối đa hoàn hảo",
        )
        assert report_max.relevance_score == 5.0
        assert report_max.overall_score == 5.0

    def test_overall_score_calculation_weights_and_auto_population(self):
        """Khẳng định: overall_score = 0.4 * relevance + 0.3 * ranking + 0.3 * faithfulness."""
        # 1. Tự động tính khi không truyền overall_score
        report_auto = RecommendationJudgeReport(
            relevance_score=4.0,
            ranking_score=5.0,
            faithfulness_score=4.0,
            rationale="Kiểm tra auto compute overall",
        )
        # 0.4 * 4.0 + 0.3 * 5.0 + 0.3 * 4.0 = 1.6 + 1.5 + 1.2 = 4.3
        expected_score = round(0.4 * 4.0 + 0.3 * 5.0 + 0.3 * 4.0, 2)
        assert report_auto.overall_score == expected_score
        assert report_auto.overall_score == 4.3

        # 2. Hàm tiện ích compute_overall_score
        assert compute_overall_score(5.0, 5.0, 5.0) == 5.0
        assert compute_overall_score(1.0, 1.0, 1.0) == 1.0
        # 0.4 * 3.5 + 0.3 * 4.2 + 0.3 * 4.8 = 1.4 + 1.26 + 1.44 = 4.10
        assert math.isclose(compute_overall_score(3.5, 4.2, 4.8), 4.10, rel_tol=1e-3)

    def test_default_factories_and_missing_rationale(self):
        """strengths và weaknesses mặc định là list rỗng; thiếu rationale ném lỗi."""
        report = RecommendationJudgeReport(
            relevance_score=3.5,
            ranking_score=3.5,
            faithfulness_score=3.5,
            rationale="Có lý giải",
        )
        assert report.strengths == []
        assert report.weaknesses == []

        with pytest.raises(ValidationError):
            RecommendationJudgeReport(  # type: ignore[call-arg]
                relevance_score=3.5,
                ranking_score=3.5,
                faithfulness_score=3.5,
                # thiếu rationale
            )


# ==============================================================================
# NHÓM 2: OFFLINE RULE-BASED JUDGE (model=None, IR & Grounding rules)
# ==============================================================================


class TestOfflineRuleBasedJudge:
    """Kiểm thử bộ trọng tài quy tắc độc lập khi chạy offline hoặc khi không có LLM."""

    @pytest.fixture
    def sample_expectation(self) -> GroundTruthExpectation:
        return GroundTruthExpectation(
            min_budget=1_500_000.0,
            max_budget=3_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=2.5,
            required_amenities=["aircon", "private_wc"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            min_area_m2=15.0,
        )

    @pytest.fixture
    def ideal_rooms(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "room_1",
                "title": "Phòng trọ cao cấp máy lạnh wc riêng gần UIT",
                "priceNum": 2_200_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "area_m2": 20.0,
                "room_type": "ROOM",
                "tags": ["máy lạnh", "wc riêng"],
                "concept_scores": {"aircon": 0.95, "private_wc": 0.90},
            },
            {
                "id": "room_2",
                "title": "Phòng trọ thoáng mát máy lạnh wc riêng",
                "priceNum": 2_500_000.0,
                "lat": 10.8730,
                "lng": 106.8040,
                "area_m2": 18.0,
                "room_type": "ROOM",
                "tags": ["máy lạnh", "wc riêng"],
                "concept_scores": {"aircon": 0.90, "private_wc": 0.85},
            },
            {
                "id": "room_3",
                "title": "Phòng trọ sinh viên tiện nghi",
                "priceNum": 2_800_000.0,
                "lat": 10.8740,
                "lng": 106.8050,
                "area_m2": 22.0,
                "room_type": "ROOM",
                "tags": ["máy lạnh", "wc riêng"],
                "concept_scores": {"aircon": 0.92, "private_wc": 0.90},
            },
        ]

    def test_ideal_recommendation_satisfies_all_expectations(
        self,
        sample_expectation: GroundTruthExpectation,
        ideal_rooms: list[dict[str, Any]],
    ):
        """Danh sách phòng lý tưởng -> relevance >= 4.0, ranking >= 4.5, overall >= 4.0."""
        text_reply = (
            "Dưới đây là 3 phòng trọ đáp ứng hoàn hảo yêu cầu của bạn gần UIT. "
            "Phòng 1 có giá 2.200.000 đ/tháng, diện tích 20m2, đầy đủ máy lạnh và vệ sinh riêng khép kín."
        )

        report = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng máy lạnh wc riêng gần UIT giá dưới 3 triệu",
            expectation=sample_expectation,
            rooms=ideal_rooms,
            text_reply=text_reply,
        )

        assert isinstance(report, RecommendationJudgeReport)
        assert report.relevance_score >= 4.5, f"Relevance score thực tế: {report.relevance_score}"
        assert report.ranking_score >= 4.5, f"Ranking score thực tế: {report.ranking_score}"
        assert report.faithfulness_score >= 4.5, f"Faithfulness score thực tế: {report.faithfulness_score}"
        assert report.overall_score >= 4.5, f"Overall score thực tế: {report.overall_score}"
        assert len(report.strengths) > 0
        assert any("100%" in s or "tuân thủ" in s.lower() for s in report.strengths)

    def test_relevance_penalty_on_hard_constraint_violations(
        self,
        sample_expectation: GroundTruthExpectation,
    ):
        """Phòng vi phạm ngân sách / khoảng cách / loại phòng cấm -> relevance bị hạ xuống <= 3.0."""
        # 1. Vi phạm giá (vượt xa ngân sách trần 3.0 triệu)
        rooms_expensive = [
            {
                "id": "r_exp",
                "title": "Căn hộ dịch vụ xa hoa",
                "priceNum": 8_500_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "area_m2": 30.0,
                "room_type": "ROOM",
            }
        ]
        rep_exp = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng dưới 3 triệu",
            expectation=sample_expectation,
            rooms=rooms_expensive,
            text_reply="Gợi ý phòng giá 8.5 triệu",
        )
        assert rep_exp.relevance_score <= 3.0
        assert any("vi phạm" in w.lower() for w in rep_exp.weaknesses)

        # 2. Vi phạm khoảng cách (quá xa > 10km, ví dụ ở Quận 10 trong khi cần gần UIT)
        rooms_far = [
            {
                "id": "r_far",
                "title": "Phòng Quận 10",
                "priceNum": 2_500_000.0,
                "lat": 10.7725,
                "lng": 106.6578,
                "area_m2": 20.0,
                "room_type": "ROOM",
            }
        ]
        rep_far = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng gần UIT",
            expectation=sample_expectation,
            rooms=rooms_far,
            text_reply="Gợi ý phòng giá 2.5 triệu ở Quận 10",
        )
        assert rep_far.relevance_score <= 3.0

        # 3. Vi phạm loại phòng cấm (SLEEPBOX khi người dùng cấm)
        rooms_sleepbox = [
            {
                "id": "r_box",
                "title": "Sleepbox KTX cao cấp",
                "priceNum": 1_800_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "area_m2": 6.0,
                "room_type": "SLEEPBOX",
            }
        ]
        rep_box = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng trọ, không ở sleepbox",
            expectation=sample_expectation,
            rooms=rooms_sleepbox,
            text_reply="Gợi ý hộp ngủ sleepbox",
        )
        assert rep_box.relevance_score <= 3.0

    def test_ranking_penalty_on_inversion(
        self,
        sample_expectation: GroundTruthExpectation,
    ):
        """Top 1 vi phạm ràng buộc cứng trong khi Top 2 đạt chuẩn -> ranking_score bị hạ xuống <= 2.0."""
        inverted_rooms = [
            # Top 1: Hỏng giá (quá đắt)
            {
                "id": "bad_top1",
                "title": "Phòng đắt đỏ",
                "priceNum": 9_000_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "room_type": "ROOM",
            },
            # Top 2: Đạt mọi tiêu chí
            {
                "id": "good_top2",
                "title": "Phòng chuẩn giá rẻ",
                "priceNum": 2_200_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "area_m2": 20.0,
                "room_type": "ROOM",
                "tags": ["máy lạnh", "wc riêng"],
                "concept_scores": {"aircon": 0.9, "private_wc": 0.9},
            },
        ]

        report = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng dưới 3 triệu",
            expectation=sample_expectation,
            rooms=inverted_rooms,
            text_reply="Danh sách phòng gợi ý",
        )

        assert report.ranking_score <= 2.0, (
            f"Khi Top 1 hỏng và Top 2 đạt, ranking_score phải <= 2.0, thực tế: {report.ranking_score}"
        )
        assert any("xếp hạng" in w.lower() for w in report.weaknesses)

    def test_empty_rooms_list_safe_handling(
        self,
        sample_expectation: GroundTruthExpectation,
    ):
        """Danh sách phòng rỗng [] không làm sập chương trình, phản hồi điểm thấp nhưng an toàn."""
        # Trường hợp 1: Có giải thích trung thực về việc không tìm thấy phòng
        text_with_explanation = (
            "Rất tiếc hiện tại hệ thống chưa tìm thấy phòng trọ nào đáp ứng đầy đủ tiêu chí của bạn. "
            "Bạn có thể cân nhắc nới lỏng ngân sách hoặc mở rộng bán kính tìm kiếm."
        )
        rep_explained = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng 1 triệu ở Quận 1",
            expectation=sample_expectation,
            rooms=[],
            text_reply=text_with_explanation,
        )

        assert isinstance(rep_explained, RecommendationJudgeReport)
        assert rep_explained.relevance_score <= 2.0
        assert rep_explained.ranking_score == 1.0
        assert rep_explained.faithfulness_score >= 4.0
        assert rep_explained.overall_score <= 3.0
        assert any("không" in w.lower() for w in rep_explained.weaknesses)

        # Trường hợp 2: Không có giải thích thỏa đáng
        rep_no_explain = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng",
            expectation=sample_expectation,
            rooms=[],
            text_reply="Xin chào tôi là trợ lý ảo.",
        )
        assert rep_no_explain.relevance_score == 1.0
        assert rep_no_explain.faithfulness_score == 2.0
        assert rep_no_explain.overall_score == 1.3

    def test_faithfulness_penalty_when_claims_hallucinated(
        self,
        sample_expectation: GroundTruthExpectation,
    ):
        """Khi câu trả lời bịa đặt số tiền không khớp với dữ liệu thực tế -> faithfulness phản ánh đúng."""
        actual_rooms = [
            {
                "id": "r1",
                "title": "Phòng giá thực tế",
                "priceNum": 2_800_000.0,
                "lat": 10.8710,
                "lng": 106.8031,
                "room_type": "ROOM",
            }
        ]

        # Bịa đặt số tiền sai lệch nghiêm trọng
        hallucinated_text = (
            "Phòng này cực kỳ rẻ, giá chỉ 1.2 triệu một tháng (hoặc 1tr2), diện tích 50m2."
        )

        report = evaluate_recommendation_quality(
            model=None,
            user_query="Tìm phòng giá rẻ",
            expectation=sample_expectation,
            rooms=actual_rooms,
            text_reply=hallucinated_text,
        )

        # faithfulness phải bị phạt giảm điểm (< 5.0)
        assert report.faithfulness_score < 5.0, (
            f"Bịa đặt giá nhưng faithfulness vẫn đạt tối đa: {report.faithfulness_score}"
        )


# ==============================================================================
# NHÓM 3: MOCKED ONLINE LLM JUDGE & AUTOMATIC FALLBACK
# ==============================================================================


class TestMockedOnlineLLMJudge:
    """Kiểm thử tương tác với mô hình LLM-as-a-Judge qua Mock và cơ chế Fallback."""

    def test_mocked_llm_structured_output_returning_report_instance(self):
        """LLM trả về RecommendationJudgeReport hợp lệ -> nhận kết quả và tính lại overall_score chuẩn."""
        mock_report = RecommendationJudgeReport(
            relevance_score=4.8,
            ranking_score=4.5,
            faithfulness_score=5.0,
            overall_score=4.8,
            strengths=["Độ chính xác cao", "Phòng Top 1 tối ưu"],
            weaknesses=[],
            rationale="Gemini Judge đánh giá chất lượng xuất sắc.",
        )

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_report

        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_chain

        res = evaluate_recommendation_quality(
            model=mock_model,
            user_query="Tìm phòng gần ĐH Bách Khoa",
            expectation=None,
            rooms=[{"id": "r1", "priceNum": 3_000_000.0}],
            text_reply="Gợi ý phòng gần Bách Khoa",
        )

        mock_model.with_structured_output.assert_called_once_with(RecommendationJudgeReport)
        mock_chain.invoke.assert_called_once()
        assert isinstance(res, RecommendationJudgeReport)
        assert res.relevance_score == 4.8
        assert res.ranking_score == 4.5
        assert res.faithfulness_score == 5.0
        # 0.4 * 4.8 + 0.3 * 4.5 + 0.3 * 5.0 = 1.92 + 1.35 + 1.50 = 4.77
        assert res.overall_score == 4.77

    def test_mocked_llm_structured_output_returning_dict(self):
        """LLM trả về kết quả dạng dictionary -> tự động parse chuẩn sang RecommendationJudgeReport."""
        mock_dict = {
            "relevance_score": 4.2,
            "ranking_score": 4.0,
            "faithfulness_score": 4.6,
            "overall_score": 4.25,
            "strengths": ["Rất tốt"],
            "weaknesses": ["Hơi xa một chút"],
            "rationale": "Chấp nhận được.",
        }

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_dict

        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_chain

        res = evaluate_recommendation_quality(
            model=mock_model,
            user_query="Tìm phòng",
            expectation=None,
            rooms=[{"id": "r1", "priceNum": 3_000_000.0}],
            text_reply="Gợi ý phòng",
        )

        assert isinstance(res, RecommendationJudgeReport)
        assert res.relevance_score == 4.2
        assert res.ranking_score == 4.0
        assert res.faithfulness_score == 4.6
        # 0.4 * 4.2 + 0.3 * 4.0 + 0.3 * 4.6 = 1.68 + 1.20 + 1.38 = 4.26
        assert res.overall_score == 4.26
        assert res.strengths == ["Rất tốt"]
        assert res.weaknesses == ["Hơi xa một chút"]

    def test_automatic_fallback_on_llm_network_or_quota_exception(self):
        """Khi LLM quăng Exception (429 Quota Exceeded, TimeoutError) -> Tự động Fallback sang Rule-based."""
        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = TimeoutError("Connection to Gemini OpenAI API endpoint timed out")

        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_chain

        exp = GroundTruthExpectation(max_budget=3_000_000.0)
        rooms = [{"id": "r1", "priceNum": 2_500_000.0, "title": "Phòng đẹp"}]

        # Phải bắt Exception trong hàm và trả về kết quả an toàn từ rule-based
        res = evaluate_recommendation_quality(
            model=mock_model,
            user_query="Tìm phòng dưới 3 triệu",
            expectation=exp,
            rooms=rooms,
            text_reply="Gợi ý phòng 2.5 triệu",
        )

        assert isinstance(res, RecommendationJudgeReport)
        # Rationale từ rule-based có dạng "Đánh giá quy tắc IR"
        assert "quy tắc IR" in res.rationale or "IR" in res.rationale
        assert res.overall_score >= 1.0

    def test_automatic_fallback_on_with_structured_output_failure(self):
        """Khi gọi with_structured_output bị lỗi ngay từ đầu -> Fallback an toàn."""
        mock_model = MagicMock()
        mock_model.with_structured_output.side_effect = RuntimeError("Model does not support structured output")

        res = evaluate_recommendation_quality(
            model=mock_model,
            user_query="Tìm phòng",
            expectation=None,
            rooms=[],
            text_reply="Không có phòng",
        )

        assert isinstance(res, RecommendationJudgeReport)
        assert res.ranking_score == 1.0

    def test_get_judge_llm_with_explicit_key_and_fallback(self):
        """get_judge_llm khởi tạo mô hình ChatOpenAI khi có key hoặc fallback an toàn."""
        # Khi truyền key giả lập
        with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
            mock_chat_openai.return_value = MagicMock()
            llm = get_judge_llm(model_name="gemini-2.5-flash-lite", api_key="sk-test-key-12345")
            assert llm is not None
            mock_chat_openai.assert_called_once()

        # Khi không có key và core.llm không khả dụng -> trả về None an toàn
        with patch.dict("os.environ", {}, clear=True):
            with patch("core.llm.get_llm", side_effect=Exception("No LLM")):
                llm_none = get_judge_llm(model_name="gemini-2.5-flash-lite", api_key="")
                assert llm_none is None or hasattr(llm_none, "invoke")


# ==============================================================================
# NHÓM 4: RUNNER FORMATTING & REPORTING
# ==============================================================================


class TestRunnerFormattingAndReporting:
    """Kiểm thử tính năng định dạng báo cáo Markdown và xuất file JSON trong run_recommendation_eval."""

    @pytest.fixture
    def sample_eval_payload(self) -> dict[str, Any]:
        """Tạo payload mẫu đầy đủ số liệu đo lường IR và Thẩm định LLM Judge."""
        meta = {
            "timestamp": "2026-11-06 17:00:00",
            "total_queries": 2,
            "judge_mode": "auto",
            "judge_model": "gemini-2.5-flash-lite",
            "budget_tolerance_pct": 0.0,
        }
        summary = {
            "total_queries": 2,
            "mean_precision_at_3": 0.85,
            "mean_precision_at_5": 0.80,
            "mrr": 0.95,
            "mean_ndcg_at_5": 0.92,
            "mean_csr": 0.82,
            "mean_price_compliance_pct": 1.0,
            "mean_distance_compliance_pct": 0.90,
            "mean_room_type_compliance_pct": 1.0,
            "mean_amenities_compliance_pct": 0.85,
            "mean_relevance_score": 4.60,
            "mean_ranking_score": 4.40,
            "mean_faithfulness_score": 4.90,
            "mean_overall_score": 4.63,
            "latency_p50_s": 1.25,
            "latency_p95_s": 2.10,
            "latency_max_s": 2.15,
            "latency_mean_s": 1.675,
        }
        group_breakdown = {
            "G1_BUDGET": {
                "count": 1,
                "mean_p3": 0.90,
                "mean_p5": 0.85,
                "mean_mrr": 1.0,
                "mean_ndcg5": 0.95,
                "mean_csr": 0.90,
                "mean_overall_score": 4.70,
                "mean_latency_s": 1.25,
            },
            "G2_SAFETY_AMENITY": {
                "count": 1,
                "mean_p3": 0.80,
                "mean_p5": 0.75,
                "mean_mrr": 0.90,
                "mean_ndcg5": 0.89,
                "mean_csr": 0.74,
                "mean_overall_score": 4.56,
                "mean_latency_s": 2.10,
            },
        }
        query_details = [
            {
                "query_id": "G1_01",
                "group": "G1_BUDGET",
                "persona_description": "Sinh viên tiết kiệm",
                "query": "Tìm phòng trọ dưới 2.5 triệu gần UIT",
                "latency_s": 1.25,
                "returned_rooms_count": 5,
                "top_room_ids": ["r1", "r2", "r3", "r4", "r5"],
                "ir_metrics": {
                    "precision_at_3": 0.90,
                    "precision_at_5": 0.85,
                    "reciprocal_rank": 1.0,
                    "ndcg_at_5": 0.95,
                    "constraint_breakdown": {
                        "overall_csr": 0.90,
                        "price_compliance_pct": 1.0,
                        "distance_compliance_pct": 1.0,
                        "room_type_compliance_pct": 1.0,
                        "area_compliance_pct": 1.0,
                        "amenities_compliance_pct": 0.90,
                    },
                },
                "judge_report": {
                    "relevance_score": 4.8,
                    "ranking_score": 4.6,
                    "faithfulness_score": 5.0,
                    "overall_score": 4.80,
                    "strengths": ["Rất tốt"],
                    "weaknesses": [],
                    "rationale": "Tuyệt vời",
                },
            },
            {
                "query_id": "G2_01",
                "group": "G2_SAFETY_AMENITY",
                "persona_description": "Nữ sinh viên ưu tiên an ninh",
                "query": "Tìm phòng có khóa vân tay gần ĐH Bách Khoa",
                "latency_s": 2.10,
                "returned_rooms_count": 4,
                "top_room_ids": ["r6", "r7", "r8", "r9"],
                "ir_metrics": {
                    "precision_at_3": 0.80,
                    "precision_at_5": 0.75,
                    "reciprocal_rank": 0.90,
                    "ndcg_at_5": 0.89,
                    "constraint_breakdown": {
                        "overall_csr": 0.74,
                        "price_compliance_pct": 1.0,
                        "distance_compliance_pct": 0.80,
                        "room_type_compliance_pct": 1.0,
                        "area_compliance_pct": 1.0,
                        "amenities_compliance_pct": 0.80,
                    },
                },
                "judge_report": {
                    "relevance_score": 4.4,
                    "ranking_score": 4.2,
                    "faithfulness_score": 4.8,
                    "overall_score": 4.46,
                    "strengths": ["Đảm bảo an ninh"],
                    "weaknesses": ["Khoảng cách hơi xa"],
                    "rationale": "Tốt",
                },
            },
        ]

        return {
            "meta": meta,
            "summary": summary,
            "group_breakdown": group_breakdown,
            "query_details": query_details,
        }

    def test_generate_markdown_report_contains_all_essential_sections(
        self,
        sample_eval_payload: dict[str, Any],
    ):
        """Báo cáo Markdown phải chứa đầy đủ 4 phần và các bảng chuẩn GFM."""
        md_text = generate_markdown_report(
            summary=sample_eval_payload["summary"],
            group_stats=sample_eval_payload["group_breakdown"],
            query_details=sample_eval_payload["query_details"],
            meta=sample_eval_payload["meta"],
        )

        assert isinstance(md_text, str)
        assert "# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)" in md_text
        assert "## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)" in md_text
        assert "### Bảng 1.1: Các chỉ số Information Retrieval (IR)" in md_text
        assert "### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge" in md_text
        assert "### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc" in md_text
        assert "### Bảng 1.4: Hiệu năng Vận hành & Độ trễ" in md_text
        assert "## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng" in md_text
        assert "## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn" in md_text
        assert "## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển" in md_text

        # Kiểm tra nội dung bảng có số liệu đúng
        assert "85.00%" in md_text  # P@3
        assert "4.63 / 5.0" in md_text  # Overall Judge Score
        assert "`G1_BUDGET`" in md_text
        assert "`G2_SAFETY_AMENITY`" in md_text
        assert "`G1_01`" in md_text
        assert "`G2_01`" in md_text

    def test_generate_markdown_report_single_dict_payload_argument(
        self,
        sample_eval_payload: dict[str, Any],
    ):
        """generate_markdown_report hỗ trợ truyền trực tiếp cả dict results_payload."""
        md_text_direct = generate_markdown_report(sample_eval_payload)
        assert isinstance(md_text_direct, str)
        assert "Báo Cáo Đánh Giá" in md_text_direct
        assert "4.63 / 5.0" in md_text_direct

    def test_build_markdown_report_alias_compatibility(
        self,
        sample_eval_payload: dict[str, Any],
    ):
        """_build_markdown_report hoạt động hoàn toàn tương thích ngược."""
        md_text = _build_markdown_report(sample_eval_payload)
        assert isinstance(md_text, str)
        assert "Báo Cáo Đánh Giá" in md_text

    def test_save_evaluation_results_creates_valid_json_and_md_files(
        self,
        sample_eval_payload: dict[str, Any],
        tmp_path: Path,
    ):
        """save_evaluation_results tạo thành công 2 file JSON và Markdown hợp lệ trên ổ đĩa."""
        json_path, md_path = save_evaluation_results(
            results_payload=sample_eval_payload,
            output_dir=tmp_path,
        )

        assert json_path.exists(), f"File JSON không tồn tại tại {json_path}"
        assert md_path.exists(), f"File Markdown không tồn tại tại {md_path}"

        # Kiểm tra đọc lại JSON hợp lệ
        with open(json_path, "r", encoding="utf-8") as f:
            loaded_json = json.load(f)

        assert "meta" in loaded_json
        assert "summary" in loaded_json
        assert "group_breakdown" in loaded_json
        assert "query_details" in loaded_json
        assert loaded_json["summary"]["mean_overall_score"] == 4.63
        assert len(loaded_json["query_details"]) == 2

        # Kiểm tra nội dung Markdown
        with open(md_path, "r", encoding="utf-8") as f:
            loaded_md = f.read()

        assert len(loaded_md) > 200
        assert "| " in loaded_md  # Chứa bảng Markdown
        assert "Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ" in loaded_md

