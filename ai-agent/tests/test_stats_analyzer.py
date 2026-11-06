"""Bộ kiểm thử Black-box độc lập cho Human Evaluation Stats Analyzer (MỐC 3).

Đặc tả: docs/features/ai-agent-recommendation-eval.md (Trụ cột 3: Human Evaluation)
Module kiểm thử:
- ai-agent/eval/stats_analyzer.py

Bao gồm 4 nhóm kiểm thử chặt chẽ theo chuẩn Black-box QA:
1. Nhóm 1: Happy Path (Thống kê mô tả đã biết trước giá trị, paired t-test và Wilcoxon trên mẫu có ý nghĩa thống kê)
2. Nhóm 2: Boundary & Edge Cases (Danh sách rỗng, 1 phần tử, 2-3 phần tử, mẫu bằng nhau diff=0, se_diff=0, kích thước không khớp, lỗi đầu vào)
3. Nhóm 3: Immutability & ASCII Boxplot Rendering (Bảo toàn list đầu vào, tính toàn vẹn ký tự biểu đồ boxplot, nhận diện thang đo)
4. Nhóm 4: Pipeline Integration & Reporting (Đọc CSV, sinh dữ liệu khoa học demo N=30, phân tích 4 câu hỏi + Overall, sinh báo cáo Markdown)
"""

from __future__ import annotations

import csv
import math
from typing import Any

import pytest

from eval.stats_analyzer import (
    QUESTION_METADATA,
    analyze_survey_data,
    compute_descriptive_stats,
    generate_ascii_boxplot,
    generate_scientific_demo_data,
    generate_survey_markdown_report,
    load_survey_from_csv,
    paired_t_test,
    run_demo_analysis,
    wilcoxon_signed_rank_test,
)


# ==============================================================================
# NHÓM 1: HAPPY PATH (LUỒNG CHUẨN & DỮ LIỆU ĐÃ BIẾT TRƯỚC GIÁ TRỊ)
# ==============================================================================


class TestDescriptiveStatsHappyPath:
    """Kiểm tra độ chính xác toán học của thống kê mô tả với các tập dữ liệu chuẩn."""

    def test_known_values_odd_sample(self):
        """Dữ liệu [1, 2, 3, 4, 5] -> mean=3.0, median=3.0, min=1.0, max=5.0, count=5."""
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        res = compute_descriptive_stats(scores)

        assert res["count"] == 5.0
        assert res["mean"] == 3.0
        assert res["median"] == 3.0
        assert res["min"] == 1.0
        assert res["max"] == 5.0
        assert res["q1"] == 2.0
        assert res["q3"] == 4.0
        assert res["iqr"] == 2.0
        # std của [1, 2, 3, 4, 5] là sqrt(2.5) ~ 1.581
        assert math.isclose(res["std"], 1.581, abs_tol=1e-3)

    def test_known_values_even_sample(self):
        """Dữ liệu [2.0, 4.0, 6.0, 8.0] -> count=4, mean=5.0, median=5.0, min=2.0, max=8.0."""
        scores = [2.0, 4.0, 6.0, 8.0]
        res = compute_descriptive_stats(scores)

        assert res["count"] == 4.0
        assert res["mean"] == 5.0
        assert res["median"] == 5.0
        assert res["min"] == 2.0
        assert res["max"] == 8.0
        assert res["q1"] == 3.5
        assert res["q3"] == 6.5
        assert res["iqr"] == 3.0

    def test_floating_point_precision(self):
        """Kiểm tra xử lý danh sách số thực với các giá trị thập phân."""
        scores = [1.25, 2.75, 3.5, 4.25, 4.75]
        res = compute_descriptive_stats(scores)

        assert res["count"] == 5.0
        assert res["mean"] == 3.3
        assert res["median"] == 3.5
        assert res["min"] == 1.25
        assert res["max"] == 4.75
        assert res["iqr"] > 0


class TestPairedTTestHappyPath:
    """Kiểm tra kiểm định giả thuyết Paired Samples t-test."""

    def test_agent_significantly_better(self):
        """Homigo Agent vượt trội hơn Baseline rõ ràng -> t_stat > 0, p_value < 0.05, is_significant=True."""
        baseline = [2.0, 2.0, 3.0, 2.0, 3.0, 2.0, 1.0, 3.0, 2.0, 3.0]
        agent = [4.0, 5.0, 5.0, 4.0, 5.0, 4.0, 4.0, 5.0, 4.0, 5.0]

        res = paired_t_test(baseline, agent, alpha=0.05)

        assert res["n"] == 10
        assert res["mean_diff"] > 2.0
        assert res["std_diff"] > 0
        assert res["se_diff"] > 0
        assert res["t_stat"] > 5.0  # t-statistic rất cao
        assert res["df"] == 9
        assert res["p_value"] < 0.001
        assert res["is_significant"] is True
        assert res["cohen_d"] > 1.5  # Large effect size

    def test_confidence_interval_contains_mean_diff(self):
        """Khoảng tin cậy 95% [ci_lower, ci_upper] phải bao trùm mean_diff."""
        baseline = [3.0, 2.0, 4.0, 3.0, 2.0, 3.0, 4.0, 3.0]
        agent = [4.0, 4.0, 5.0, 4.0, 4.0, 5.0, 5.0, 4.0]

        res = paired_t_test(baseline, agent)
        ci_lower, ci_upper = res["ci_95"]

        assert ci_lower < res["mean_diff"] < ci_upper
        assert ci_lower > 0  # Toàn bộ khoảng tin cậy dương thể hiện cải thiện rõ rệt


class TestWilcoxonSignedRankHappyPath:
    """Kiểm tra kiểm định phi tham số Wilcoxon Signed-Rank Test."""

    def test_agent_significantly_better_wilcoxon(self):
        """Khi Agent vượt trội hơn Baseline, w_plus áp đảo w_minus, z_score > 0, p_value < 0.05."""
        baseline = [2.0, 2.0, 3.0, 2.0, 3.0, 2.0, 1.0, 3.0, 2.0, 3.0]
        agent = [4.0, 5.0, 5.0, 4.0, 5.0, 4.0, 4.0, 5.0, 4.0, 5.0]

        res = wilcoxon_signed_rank_test(baseline, agent, alpha=0.05)

        assert res["n_pairs"] == 10
        assert res["n_nonzero"] == 10
        assert res["w_plus"] > 0
        assert res["w_minus"] == 0.0  # Toàn bộ chênh lệch đều dương
        assert res["w_stat"] == 0.0
        assert res["z_score"] > 0
        assert res["p_value"] < 0.01
        assert res["is_significant"] is True

    def test_wilcoxon_with_tied_ranks(self):
        """Kiểm tra thuật toán xử lý đồng hạng (tie averaging) khi nhiều cặp có cùng độ chênh lệch."""
        baseline = [2.0, 2.0, 3.0, 3.0, 2.0, 1.0]
        agent = [4.0, 4.0, 5.0, 5.0, 4.0, 3.0]  # Mọi diff đều bằng +2.0

        res = wilcoxon_signed_rank_test(baseline, agent)
        assert res["n_nonzero"] == 6
        assert res["w_minus"] == 0.0
        # 6 hạng đồng hạng từ 1..6 -> rank mỗi phần tử = (1+6)/2 = 3.5 -> tổng w_plus = 21.0
        assert res["w_plus"] == 21.0
        assert res["is_significant"] is True


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES (DỮ LIỆU BIÊN, RỖNG & ĐỘT BIẾN)
# ==============================================================================


class TestDescriptiveStatsEdgeCases:
    """Kiểm tra các trường hợp biên của thống kê mô tả: rỗng, 1 phần tử, 2 phần tử, 3 phần tử."""

    def test_empty_scores_returns_safe_zero_dict(self):
        """Mảng rỗng [] không được văng ZeroDivisionError, phải trả dict an toàn có count=0."""
        res = compute_descriptive_stats([])
        assert res["count"] == 0.0
        assert res["mean"] == 0.0
        assert res["std"] == 0.0
        assert res["median"] == 0.0
        assert res["q1"] == 0.0
        assert res["q3"] == 0.0
        assert res["iqr"] == 0.0
        assert res["min"] == 0.0
        assert res["max"] == 0.0

    def test_single_element_sample(self):
        """Mảng có 1 phần tử [4.5] -> std=0.0, min=max=median=q1=q3=4.5, iqr=0.0."""
        res = compute_descriptive_stats([4.5])
        assert res["count"] == 1.0
        assert res["mean"] == 4.5
        assert res["std"] == 0.0
        assert res["median"] == 4.5
        assert res["q1"] == 4.5
        assert res["q3"] == 4.5
        assert res["iqr"] == 0.0
        assert res["min"] == 4.5
        assert res["max"] == 4.5

    def test_two_elements_sample(self):
        """Mảng 2 phần tử [2.0, 6.0] -> count=2, mean=4.0, median=4.0, q1=2.0, q3=6.0, iqr=4.0."""
        res = compute_descriptive_stats([2.0, 6.0])
        assert res["count"] == 2.0
        assert res["mean"] == 4.0
        assert res["median"] == 4.0
        assert res["q1"] == 2.0
        assert res["q3"] == 6.0
        assert res["iqr"] == 4.0
        assert math.isclose(res["std"], math.sqrt(8.0), abs_tol=1e-3)

    def test_three_elements_sample(self):
        """Mảng 3 phần tử [1.0, 3.0, 9.0] -> median=3.0, q1=1.0, q3=9.0, iqr=8.0."""
        res = compute_descriptive_stats([1.0, 3.0, 9.0])
        assert res["count"] == 3.0
        assert res["median"] == 3.0
        assert res["q1"] == 1.0
        assert res["q3"] == 9.0
        assert res["iqr"] == 8.0

    def test_identical_elements_sample(self):
        """Mảng toàn phần tử giống nhau [3.0, 3.0, 3.0, 3.0] -> std=0, iqr=0."""
        res = compute_descriptive_stats([3.0, 3.0, 3.0, 3.0])
        assert res["mean"] == 3.0
        assert res["std"] == 0.0
        assert res["iqr"] == 0.0
        assert res["min"] == 3.0
        assert res["max"] == 3.0


class TestPairedTTestEdgeCases:
    """Kiểm tra các tình huống biên và lỗi tham số của paired t-test."""

    def test_identical_arrays_no_difference(self):
        """Hai mảng giống hệt nhau -> mean_diff=0, t_stat=0.0, p_value=1.0, is_significant=False."""
        baseline = [3.0, 4.0, 3.0, 5.0, 2.0]
        agent = [3.0, 4.0, 3.0, 5.0, 2.0]

        res = paired_t_test(baseline, agent)
        assert res["mean_diff"] == 0.0
        assert res["se_diff"] == 0.0
        assert res["t_stat"] == 0.0
        assert res["p_value"] == 1.0
        assert res["is_significant"] is False

    def test_constant_positive_difference(self):
        """Mọi cặp đều có độ chênh lệch không đổi d > 0 -> se_diff=0, t_stat=inf, p_value=0.0001, is_significant=True."""
        baseline = [1.0, 2.0, 3.0, 4.0]
        agent = [2.0, 3.0, 4.0, 5.0]  # Luôn chênh +1.0

        res = paired_t_test(baseline, agent)
        assert res["mean_diff"] == 1.0
        assert res["se_diff"] == 0.0
        assert math.isinf(res["t_stat"]) and res["t_stat"] > 0
        assert res["p_value"] == 0.0001
        assert res["is_significant"] is True

    def test_constant_negative_difference(self):
        """Mọi cặp đều có độ chênh lệch không đổi d < 0 -> se_diff=0, t_stat=-inf, p_value=0.0001."""
        baseline = [5.0, 4.0, 3.0]
        agent = [4.0, 3.0, 2.0]  # Luôn chênh -1.0

        res = paired_t_test(baseline, agent)
        assert res["mean_diff"] == -1.0
        assert res["se_diff"] == 0.0
        assert math.isinf(res["t_stat"]) and res["t_stat"] < 0
        assert res["p_value"] == 0.0001

    def test_mismatched_lengths_raises_value_error(self):
        """Độ dài hai mảng khác nhau -> ném ValueError với thông điệp rõ ràng."""
        baseline = [1.0, 2.0, 3.0]
        agent = [1.0, 2.0]

        with pytest.raises(ValueError, match="Kích thước mẫu không khớp"):
            paired_t_test(baseline, agent)

    def test_sample_size_less_than_two_raises_value_error(self):
        """Kích thước mẫu < 2 không thể tính bậc tự do t-test -> ném ValueError."""
        with pytest.raises(ValueError, match="Cần tối thiểu 2 cặp quan sát"):
            paired_t_test([3.0], [4.0])


class TestWilcoxonEdgeCases:
    """Kiểm tra các tình huống biên của Wilcoxon Signed-Rank Test."""

    def test_identical_arrays_all_zero_diffs(self):
        """Hai mảng bằng nhau hoàn toàn -> diffs toàn 0 -> n_nonzero=0, p_value=1.0, is_significant=False."""
        baseline = [3.0, 4.0, 5.0, 2.0]
        agent = [3.0, 4.0, 5.0, 2.0]

        res = wilcoxon_signed_rank_test(baseline, agent)
        assert res["n_pairs"] == 4
        assert res["n_nonzero"] == 0
        assert res["w_plus"] == 0.0
        assert res["w_minus"] == 0.0
        assert res["w_stat"] == 0.0
        assert res["z_score"] == 0.0
        assert res["p_value"] == 1.0
        assert res["is_significant"] is False

    def test_mismatched_lengths_raises_value_error(self):
        """Độ dài khác nhau -> ném ValueError."""
        with pytest.raises(ValueError, match="phải bằng nhau"):
            wilcoxon_signed_rank_test([1.0, 2.0], [1.0])

    def test_agent_worse_than_baseline(self):
        """Trường hợp Baseline vượt trội hơn Agent -> w_minus áp đảo, z_score < 0, p_value < 0.05."""
        baseline = [5.0, 5.0, 4.0, 5.0, 4.0, 5.0, 5.0, 4.0]
        agent = [2.0, 1.0, 2.0, 2.0, 1.0, 2.0, 1.0, 2.0]

        res = wilcoxon_signed_rank_test(baseline, agent)
        assert res["w_minus"] > res["w_plus"]
        assert res["w_plus"] == 0.0
        assert res["z_score"] < -2.0
        assert res["p_value"] < 0.05
        assert res["is_significant"] is True


# ==============================================================================
# NHÓM 3: IMMUTABILITY & ASCII BOXPLOT RENDERING (BẢO TOÀN TRẠNG THÁI & HIỂN THỊ)
# ==============================================================================


class TestImmutabilityAndRendering:
    """Kiểm tra tính bất biến của mảng đầu vào và độ hợp lệ của chuỗi ASCII Boxplot."""

    def test_input_lists_are_not_mutated(self):
        """Các hàm không được sửa đổi, tráo đổi hoặc sắp xếp in-place mảng gốc của caller."""
        original_base = [5.0, 1.0, 3.0, 4.0, 2.0]
        original_agent = [2.0, 5.0, 4.0, 1.0, 3.0]

        base_copy = list(original_base)
        agent_copy = list(original_agent)

        compute_descriptive_stats(base_copy)
        assert base_copy == original_base

        paired_t_test(base_copy, agent_copy)
        assert base_copy == original_base
        assert agent_copy == original_agent

        wilcoxon_signed_rank_test(base_copy, agent_copy)
        assert base_copy == original_base
        assert agent_copy == original_agent

        generate_ascii_boxplot(base_copy, agent_copy)
        assert base_copy == original_base
        assert agent_copy == original_agent

    def test_tuple_and_range_compatibility(self):
        """Kiểm tra khả năng tiếp nhận Sequence bất kỳ (tuple, range) ngoài list thông thường."""
        base_tuple = (2.0, 3.0, 4.0, 2.0)
        agent_tuple = (4.0, 5.0, 5.0, 4.0)

        desc = compute_descriptive_stats(base_tuple)
        assert desc["count"] == 4.0

        t_res = paired_t_test(base_tuple, agent_tuple)
        assert t_res["n"] == 4

        w_res = wilcoxon_signed_rank_test(base_tuple, agent_tuple)
        assert w_res["n_pairs"] == 4

    def test_ascii_boxplot_structure_and_labels(self):
        """Biểu đồ ASCII Boxplot phải xuất chuỗi hợp lệ gồm Baseline, Homigo, Thang Điểm và các ký tự hộp."""
        baseline = [2.0, 2.5, 3.0, 3.5, 4.0]
        agent = [4.0, 4.5, 4.5, 5.0, 5.0]

        boxplot_str = generate_ascii_boxplot(baseline, agent, width=40)

        assert isinstance(boxplot_str, str)
        assert "Baseline (A) :" in boxplot_str
        assert "Homigo   (B) :" in boxplot_str
        assert "Thang Điểm   :" in boxplot_str
        assert "Med:" in boxplot_str
        assert "Mean:" in boxplot_str

        # Các ký tự cấu thành biểu đồ hộp
        assert "[" in boxplot_str  # Q1
        assert "]" in boxplot_str  # Q3
        assert "|" in boxplot_str  # Median / Min / Max
        assert "=" in boxplot_str  # IQR box body
        assert "-" in boxplot_str  # Whiskers
        assert "^" in boxplot_str  # Scale ticks


# ==============================================================================
# NHÓM 4: PIPELINE INTEGRATION & REPORTING (TÍCH HỢP TOÀN DIỆN & BÁO CÁO)
# ==============================================================================


class TestSurveyPipelineAndReporting:
    """Kiểm tra toàn bộ pipeline: nạp CSV, sinh dữ liệu demo, tính toán 4 câu hỏi + Overall, sinh Markdown."""

    def test_question_metadata_integrity(self):
        """Khẳng định đủ 4 câu hỏi nghiên cứu chuẩn: Q1, Q2, Q3, Q4."""
        expected_keys = {"Q1", "Q2", "Q3", "Q4"}
        assert set(QUESTION_METADATA.keys()) == expected_keys

        for q_key, meta in QUESTION_METADATA.items():
            assert "title" in meta
            assert "name_en" in meta
            assert "description" in meta
            assert len(meta["title"]) > 0

    def test_generate_scientific_demo_data_integrity(self):
        """Sinh dữ liệu khoa học N=30: đủ 4 câu hỏi, n_samples=30, điểm trong khoảng [1.0, 5.0]."""
        demo_data = generate_scientific_demo_data(n_samples=30, seed=42)

        assert set(demo_data.keys()) == {"Q1", "Q2", "Q3", "Q4"}
        for q_key, pair in demo_data.items():
            assert "baseline" in pair
            assert "agent" in pair
            assert len(pair["baseline"]) == 30
            assert len(pair["agent"]) == 30

            # Tất cả điểm số nằm trong thang Likert 1-5
            assert all(1.0 <= s <= 5.0 for s in pair["baseline"])
            assert all(1.0 <= s <= 5.0 for s in pair["agent"])

    def test_run_demo_analysis_statistical_significance(self):
        """Chạy demo analysis N=30: p_value < 0.05 và t_stat > 0 trên cả 4 câu hỏi và Overall."""
        res = run_demo_analysis(n_samples=30, seed=42)

        assert res["sample_size"] == 30
        assert "questions" in res
        assert "overall" in res
        assert len(res["questions"]) == 4

        for q_key in ["Q1", "Q2", "Q3", "Q4"]:
            q_res = res["questions"][q_key]
            t_test = q_res["paired_t_test"]
            wilcoxon = q_res["wilcoxon"]

            # Kiểm tra ý nghĩa thống kê vượt trội của Homigo Agent
            assert t_test["mean_diff"] > 0
            assert t_test["t_stat"] > 0
            assert t_test["p_value"] < 0.05
            assert t_test["is_significant"] is True

            assert wilcoxon["z_score"] > 0
            assert wilcoxon["p_value"] < 0.05
            assert wilcoxon["is_significant"] is True

        # Kiểm tra phần Overall
        ov_t = res["overall"]["paired_t_test"]
        ov_w = res["overall"]["wilcoxon"]
        assert ov_t["n"] == 120  # 30 * 4 câu
        assert ov_t["mean_diff"] > 1.0
        assert ov_t["p_value"] < 0.001
        assert ov_w["p_value"] < 0.001

    def test_generate_survey_markdown_report_formatting(self):
        """Báo cáo Markdown phải chứa đủ 4 phần mục chính và bảng đối chiếu tiêu chuẩn."""
        results = run_demo_analysis(n_samples=30, seed=42)
        report_md = generate_survey_markdown_report(results, title="Báo Cáo Khảo Sát Tốt Nghiệp")

        assert "# 📊 Báo Cáo Khảo Sát Tốt Nghiệp" in report_md
        assert "N = 30 sinh viên" in report_md
        assert "## 1. 📈 Thống Kê Mô Tả" in report_md
        assert "## 2. 🧪 Kiểm Định Giả Thuyết Thống Kê" in report_md
        assert "## 3. 📦 Biểu Đồ Phân Vị Trực Quan" in report_md
        assert "## 4. 🎓 Nhận Định Khoa Học & Kết Luận Nghiên Cứu" in report_md

        # Có bảng biểu đối chiếu Q1 -> Q4 và TỔNG THỂ
        for q_key in ["Q1", "Q2", "Q3", "Q4"]:
            assert q_key in report_md
        assert "🏆 **TỔNG THỂ" in report_md
        assert "Paired Samples $t$-test" in report_md
        assert "Wilcoxon Signed-Rank Test" in report_md

    def test_load_survey_from_csv_success(self, tmp_path):
        """Kiểm tra đọc file CSV khảo sát thực tế thành công qua tmp_path."""
        csv_file = tmp_path / "test_human_eval.csv"
        rows = [
            {
                "q1_baseline": "3.0",
                "q1_agent": "5.0",
                "q2_baseline": "2.0",
                "q2_agent": "4.0",
                "q3_baseline": "3.0",
                "q3_agent": "4.0",
                "q4_baseline": "3.0",
                "q4_agent": "5.0",
            },
            {
                "q1_baseline": "2.0",
                "q1_agent": "4.0",
                "q2_baseline": "3.0",
                "q2_agent": "5.0",
                "q3_baseline": "4.0",
                "q3_agent": "5.0",
                "q4_baseline": "2.0",
                "q4_agent": "4.0",
            },
        ]
        with open(csv_file, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        loaded_data = load_survey_from_csv(str(csv_file))
        assert set(loaded_data.keys()) == {"Q1", "Q2", "Q3", "Q4"}
        assert loaded_data["Q1"]["baseline"] == [3.0, 2.0]
        assert loaded_data["Q1"]["agent"] == [5.0, 4.0]
        assert loaded_data["Q2"]["baseline"] == [2.0, 3.0]
        assert loaded_data["Q2"]["agent"] == [4.0, 5.0]

    def test_load_survey_from_csv_file_not_found(self):
        """Đọc tệp CSV không tồn tại phải ném FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Không tìm thấy file CSV"):
            load_survey_from_csv("non_existent_survey_file.csv")

    def test_analyze_survey_data_partial_questions(self):
        """Xử lý an toàn khi chỉ có 2/4 câu hỏi được cung cấp."""
        partial_data = {
            "Q1": {"baseline": [2.0, 3.0, 2.0], "agent": [4.0, 5.0, 4.0]},
            "Q2": {"baseline": [2.0, 2.0, 3.0], "agent": [4.0, 4.0, 5.0]},
        }
        res = analyze_survey_data(partial_data)

        assert res["sample_size"] == 3
        assert len(res["questions"]) == 2
        assert "Q1" in res["questions"]
        assert "Q2" in res["questions"]
        assert "Q3" not in res["questions"]
        assert "overall" in res
