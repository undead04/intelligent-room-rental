"""Black-box test cho toàn bộ hệ thống Evaluate (Eval Set, Trajectory, pass^k, Regression)."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval import report, run as eval_cli
from eval.datasets.agent_eval_set import (
    AGENT_EVAL_CASES,
    AGENT_REQUIREMENTS,
    EVAL_SET_CHANGELOG,
    EVAL_SET_VERSION,
    FaultInjection,
    TrajectorySpec,
    compute_eval_set_digest,
    validate_eval_set_coverage,
)
from eval.metrics import rate
from eval.stability_and_regression import (
    compare_regression,
    diff_traces_first_divergence,
    run_repeated_eval,
)
from eval.trajectory import grade_trajectory, validate_trace_gradable


# ---------------------------------------------------------------------------
# Helpers dựng dữ liệu test độc lập (Anti-Cheating)
# ---------------------------------------------------------------------------

def _span(
    seq: int,
    span_type: str,
    *,
    run_id: str = "run-1",
    case_id: str = "case-1",
    **extra: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_id": run_id,
        "case_id": case_id,
        "seq": seq,
        "ts": "2026-11-15T00:00:00+00:00",
        "type": span_type,
        "versions": {"prompt": "p-v1", "skill": "s-v1", "model": "m-v1"},
    }
    out.update(extra)
    return out


def _synthetic_eval_result(
    *,
    case_outcomes: dict[str, tuple[int, int]],
    versions: dict[str, str],
    digest: str = "digest-fixed-123",
    pass_threshold: float = 0.5,
) -> dict[str, Any]:
    cases_list: list[dict[str, Any]] = []
    k = next(iter(case_outcomes.values()))[1]
    pass_all_k_cnt = 0
    total_passes = 0
    total_runs = 0
    for cid, (p_cnt, case_k) in case_outcomes.items():
        passed_all_k = p_cnt == case_k
        if passed_all_k:
            pass_all_k_cnt += 1
        total_passes += p_cnt
        total_runs += case_k
        cases_list.append({
            "case_id": cid,
            "category": "normal",
            "target_requirements": ["req_hybrid_search"],
            "passed_all_k": passed_all_k,
            "pass_count": p_cnt,
            "k": case_k,
            "unstable": 0 < p_cnt < case_k,
            "first_divergence": None,
            "failure_reasons": ([] if passed_all_k else [f"{cid}: fail"]),
            "runs": [
                {
                    "run_index": idx,
                    "run_id": f"{cid}-r{idx}",
                    "versions": dict(versions),
                    "passed": idx < p_cnt,
                    "trace_spans": [
                        _span(
                            1,
                            "model_call",
                            run_id=f"{cid}-r{idx}",
                            case_id=cid,
                            versions=dict(versions),
                            input="test-in",
                            output="test-out",
                        )
                    ],
                }
                for idx in range(case_k)
            ],
        })

    n = len(case_outcomes)
    return {
        "pre_run_declaration": {
            "k": k,
            "pass_threshold": pass_threshold,
            "dataset_version": EVAL_SET_VERSION,
            "dataset_digest": digest,
            "n_cases": n,
            "declared_before_execution": True,
        },
        "dataset_version": EVAL_SET_VERSION,
        "dataset_digest": digest,
        "versions": dict(versions),
        "summary": {
            "pass_all_k_rate": rate(pass_all_k_cnt, n),
            "mean_pass_rate": rate(total_passes, total_runs),
            "trajectory_pass_rate": rate(total_passes, total_runs),
            "sufficient_steps_rate": rate(total_runs, total_runs),
            "no_forbidden_or_redundant_rate": rate(total_runs, total_runs),
            "dod_pass_rate": rate(total_passes, total_runs),
            "unstable_case_count": sum(1 for c in cases_list if c["unstable"]),
            "meets_threshold": (pass_all_k_cnt / n) >= pass_threshold,
        },
        "unstable_cases": [c for c in cases_list if c["unstable"]],
        "cases": cases_list,
    }


# ---------------------------------------------------------------------------
# A. Eval Set & Coverage Tests
# ---------------------------------------------------------------------------

def test_eval_set_covers_all_requirements_and_categories() -> None:
    issues = validate_eval_set_coverage(AGENT_EVAL_CASES, AGENT_REQUIREMENTS)
    assert issues == [], f"Eval set thiếu phủ sóng hoặc thiếu thông tin: {issues}"

    categories = {c.category for c in AGENT_EVAL_CASES}
    assert categories == {"normal", "boundary", "missing_info", "conflict", "tool_error", "out_of_scope"}

    targeted_reqs = {req for c in AGENT_EVAL_CASES for req in c.target_requirements}
    assert set(AGENT_REQUIREMENTS.keys()).issubset(targeted_reqs)

    # Mọi case phải có đủ đầu vào, trạng thái đầu, fault_injection, kỳ vọng và verdict_criteria
    for case in AGENT_EVAL_CASES:
        assert case.turns, f"{case.case_id} thiếu turns"
        assert case.initial_state is not None
        assert case.fault_injection is not None
        assert case.expected is not None
        assert case.verdict_criteria.strip()

    # Changelog giải trình rõ thêm/sửa/loại
    actions = {entry["action"] for entry in EVAL_SET_CHANGELOG}
    assert {"added", "modified_from_legacy", "removed_legacy"}.issubset(actions)
    for entry in EVAL_SET_CHANGELOG:
        assert str(entry.get("reason") or "").strip()
        assert entry.get("case_ids")

    # Digest bất biến và nhạy thay đổi
    d1 = compute_eval_set_digest(AGENT_EVAL_CASES)
    d2 = compute_eval_set_digest(AGENT_EVAL_CASES)
    assert d1 == d2
    modified_cases = [replace(AGENT_EVAL_CASES[0], turns=("khác hoàn toàn",)), *AGENT_EVAL_CASES[1:]]
    assert compute_eval_set_digest(modified_cases) != d1


def test_full_agent_eval_set_passes_repeated_runs() -> None:
    versions = {"prompt": "v2.1.0", "skill": "housing-v1", "model": "eval-deterministic-v1"}
    res = run_repeated_eval(
        AGENT_EVAL_CASES,
        k=2,
        pass_threshold=0.95,
        versions_override=versions,
    )

    decl = res["pre_run_declaration"]
    assert decl["declared_before_execution"] is True
    assert decl["k"] == 2
    assert decl["pass_threshold"] == 0.95
    assert decl["dataset_digest"] == compute_eval_set_digest(AGENT_EVAL_CASES)
    assert res["versions"] == versions

    failed = [c for c in res["cases"] if not c["passed_all_k"]]
    assert not failed, (
        "Các case thất bại trong run_repeated_eval: "
        + "; ".join(f"{c['case_id']} -> {c['failure_reasons']}" for c in failed)
    )
    assert res["summary"]["pass_all_k_rate"]["rate"] == 1.0
    assert res["summary"]["meets_threshold"] is True
    assert res["unstable_cases"] == []


# ---------------------------------------------------------------------------
# B. Trajectory Grading Tests
# ---------------------------------------------------------------------------

def test_trajectory_permits_multiple_valid_tool_orders() -> None:
    spec = TrajectorySpec(
        required_tools=("resolve_location", "search_rooms"),
        required_arg_keys={"search_rooms": ("city", "lat")},
        forbidden_tools=("get_listing_detail",),
        max_calls_per_tool={"resolve_location": 1, "search_rooms": 1},
    )

    trace_a = [
        _span(1, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
        _span(2, "tool_call", tool="search_rooms", args={"city": "HCM", "lat": 10.87}),
    ]
    trace_b = [
        _span(1, "tool_call", tool="search_rooms", args={"city": "HCM", "lat": 10.87}),
        _span(2, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
    ]

    grade_a = grade_trajectory(trace_a, spec)
    grade_b = grade_trajectory(trace_b, spec)
    assert grade_a.gradable and grade_a.passed
    assert grade_a.sufficient_required_steps and grade_a.no_forbidden_or_redundant_steps
    assert grade_b.gradable and grade_b.passed
    assert grade_b.sufficient_required_steps and grade_b.no_forbidden_or_redundant_steps


def test_trajectory_separates_q1_sufficient_and_q2_forbidden_or_redundant() -> None:
    spec = TrajectorySpec(
        required_tools=("resolve_location", "search_rooms"),
        required_arg_keys={"search_rooms": ("city", "lat")},
        forbidden_tools=("get_listing_detail",),
        max_calls_per_tool={"resolve_location": 1, "search_rooms": 2},
    )

    # 1. Thiếu bước bắt buộc -> Q1=False, Q2=True
    missing_tool_trace = [
        _span(1, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
    ]
    g_missing = grade_trajectory(missing_tool_trace, spec)
    assert g_missing.gradable is True
    assert g_missing.sufficient_required_steps is False
    assert g_missing.no_forbidden_or_redundant_steps is True
    assert "search_rooms" in g_missing.missing_required_steps
    assert g_missing.passed is False

    # 2. Thiếu tham số bắt buộc của tool -> Q1=False, Q2=True
    missing_arg_trace = [
        _span(1, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
        _span(2, "tool_call", tool="search_rooms", args={"city": "HCM"}),
    ]
    g_arg = grade_trajectory(missing_arg_trace, spec)
    assert g_arg.sufficient_required_steps is False
    assert g_arg.no_forbidden_or_redundant_steps is True
    assert "search_rooms.lat" in g_arg.missing_arg_details
    assert g_arg.passed is False

    # 3. Đủ bước bắt buộc nhưng gọi tool cấm -> Q1=True, Q2=False
    forbidden_trace = [
        _span(1, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
        _span(2, "tool_call", tool="search_rooms", args={"city": "HCM", "lat": 10.87}),
        _span(3, "tool_call", tool="get_listing_detail", args={"room_id": 1}),
    ]
    g_forbid = grade_trajectory(forbidden_trace, spec)
    assert g_forbid.sufficient_required_steps is True
    assert g_forbid.no_forbidden_or_redundant_steps is False
    assert g_forbid.forbidden_violations
    assert g_forbid.passed is False

    # 4. Đủ bước bắt buộc nhưng lặp tool y hệt args (thừa bước) -> Q1=True, Q2=False
    redundant_trace = [
        _span(1, "tool_call", tool="resolve_location", args={"place": "Linh Trung"}),
        _span(2, "tool_call", tool="search_rooms", args={"city": "HCM", "lat": 10.87}),
        _span(3, "tool_call", tool="search_rooms", args={"city": "HCM", "lat": 10.87}),
    ]
    g_red = grade_trajectory(redundant_trace, spec)
    assert g_red.sufficient_required_steps is True
    assert g_red.no_forbidden_or_redundant_steps is False
    assert g_red.redundant_steps
    assert g_red.passed is False


@pytest.mark.parametrize(
    "bad_tool_span",
    [
        {"type": "tool_call", "tool": "search_rooms", "args": {"city": "HCM"}},  # thiếu seq
        {"seq": 1, "type": "tool_call", "tool": "", "args": {"city": "HCM"}},  # thiếu tên tool
        {"seq": 1, "type": "tool_call", "tool": "search_rooms"},  # thiếu args
    ],
)
def test_trajectory_ungradable_when_trace_missing_order_tool_or_args(bad_tool_span: dict[str, Any]) -> None:
    spec = TrajectorySpec(required_tools=("search_rooms",))
    ok, errs = validate_trace_gradable([bad_tool_span])
    assert ok is False and errs

    grade = grade_trajectory([bad_tool_span], spec)
    assert grade.gradable is False
    assert grade.passed is False
    assert grade.gradability_errors


# ---------------------------------------------------------------------------
# C. Repeated Runs (pass^k) & First-Divergence Trace Diff Tests
# ---------------------------------------------------------------------------

def test_repeated_runs_detects_unstable_case_and_pins_first_divergence() -> None:
    base_case = next(c for c in AGENT_EVAL_CASES if c.case_id == "norm_place_search")
    unstable_case = replace(base_case, fault_injection=FaultInjection(unreliable_llm_every_n=2))

    res = run_repeated_eval(
        [unstable_case],
        k=3,
        pass_threshold=0.9,
        versions_override={"prompt": "v-unstable", "skill": "housing-v1", "model": "flaky-sim"},
    )

    assert res["pre_run_declaration"]["k"] == 3
    assert res["pre_run_declaration"]["pass_threshold"] == 0.9
    assert res["pre_run_declaration"]["declared_before_execution"] is True
    assert res["summary"]["pass_all_k_rate"]["rate"] == 0.0
    assert res["summary"]["meets_threshold"] is False
    assert res["summary"]["unstable_case_count"] == 1
    assert len(res["unstable_cases"]) == 1

    uc = res["unstable_cases"][0]
    assert uc["case_id"] == "norm_place_search"
    assert uc["pass_count"] == 2
    assert len(uc["run_ids"]) == 3

    div = uc["first_divergence"]
    assert div["diverged"] is True
    assert div["trace_metadata_complete"] is True
    assert div["case_id"] == "norm_place_search"
    assert div["run_id_a"] != div["run_id_b"]
    assert div["step_type"] == "model_call"
    assert div["first_diff_index"] == 0
    assert "output" in div["diff_fields"]


def test_diff_traces_flags_incomplete_trace_metadata() -> None:
    t1 = [{"seq": 1, "type": "model_call", "input": "hi", "output": "ok"}]  # thiếu run_id & case_id
    t2 = [{"seq": 1, "type": "model_call", "run_id": "r2", "case_id": "c1", "output": "diff"}]  # thiếu input
    diff = diff_traces_first_divergence(t1, t2)
    assert diff["diverged"] is True
    assert diff["trace_metadata_complete"] is False
    assert diff["missing_trace_metadata"]


# ---------------------------------------------------------------------------
# D. Regression Gate, Digest Lock & Version Attribution Tests
# ---------------------------------------------------------------------------

def test_regression_rejects_mismatched_eval_set_digest() -> None:
    base = _synthetic_eval_result(
        case_outcomes={"c1": (2, 2)},
        versions={"prompt": "p1", "skill": "s1", "model": "m1"},
        digest="digest-A",
    )
    curr = _synthetic_eval_result(
        case_outcomes={"c1": (2, 2)},
        versions={"prompt": "p2", "skill": "s1", "model": "m1"},
        digest="digest-B",
    )
    with pytest.raises(ValueError, match="Eval set bị thay đổi"):
        compare_regression(base, curr)


def test_regression_rejects_even_if_aggregate_improves_when_any_case_regresses() -> None:
    # Tổng pass_all_k_rate TĂNG từ 2/4 (50%) lên 3/4 (75%), vượt ngưỡng 50%,
    # nhưng case "c3" chuyển từ ĐẠT -> RỚT => BẮT BUỘC REJECT!
    base = _synthetic_eval_result(
        case_outcomes={"c1": (0, 2), "c2": (0, 2), "c3": (2, 2), "c4": (2, 2)},
        versions={"prompt": "prompt-v1", "skill": "skill-v1", "model": "model-v1"},
        pass_threshold=0.5,
    )
    curr = _synthetic_eval_result(
        case_outcomes={"c1": (2, 2), "c2": (2, 2), "c3": (1, 2), "c4": (2, 2)},
        versions={"prompt": "prompt-v2", "skill": "skill-v1", "model": "model-v2"},
        pass_threshold=0.5,
    )

    reg = compare_regression(base, curr, pass_threshold=0.5)
    assert reg["metrics_comparison"]["pass_all_k_rate"] == {
        "baseline": 0.5,
        "current": 0.75,
        "delta": 0.25,
    }
    assert [c["case_id"] for c in reg["regressed_cases"]] == ["c3"]
    assert [c["case_id"] for c in reg["improved_cases"]] == ["c1", "c2"]
    assert reg["changed_versions"] == {
        "model": {"baseline": "model-v1", "current": "model-v2"},
        "prompt": {"baseline": "prompt-v1", "current": "prompt-v2"},
    }
    assert reg["decision"] == "REJECT"
    assert "c3" in reg["decision_rationale"]
    assert "pass_all_k_rate" in reg["basis_metrics"]


def test_regression_keeps_when_zero_regressions_and_meets_threshold() -> None:
    base = _synthetic_eval_result(
        case_outcomes={"c1": (1, 2), "c2": (2, 2)},
        versions={"prompt": "prompt-v1", "skill": "skill-v1", "model": "model-v1"},
        pass_threshold=0.8,
    )
    curr = _synthetic_eval_result(
        case_outcomes={"c1": (2, 2), "c2": (2, 2)},
        versions={"prompt": "prompt-v2", "skill": "skill-v2", "model": "model-v1"},
        pass_threshold=0.8,
    )

    reg = compare_regression(base, curr, pass_threshold=0.8)
    assert reg["regressed_cases"] == []
    assert [c["case_id"] for c in reg["improved_cases"]] == ["c1"]
    assert reg["changed_versions"] == {
        "prompt": {"baseline": "prompt-v1", "current": "prompt-v2"},
        "skill": {"baseline": "skill-v1", "current": "skill-v2"},
    }
    assert reg["decision"] == "KEEP"
    assert "pass_all_k_rate" in reg["decision_rationale"]


# ---------------------------------------------------------------------------
# E. Report Markdown & CLI Integration Tests
# ---------------------------------------------------------------------------

def test_report_renders_agent_eval_and_regression_sections() -> None:
    base = _synthetic_eval_result(
        case_outcomes={"c1": (0, 2), "c2": (2, 2)},
        versions={"prompt": "v1", "skill": "s1", "model": "m1"},
    )
    curr = _synthetic_eval_result(
        case_outcomes={"c1": (2, 2), "c2": (2, 2)},
        versions={"prompt": "v2", "skill": "s1", "model": "m1"},
    )
    reg = compare_regression(base, curr, pass_threshold=0.8)
    md = report.build_report({"agent_eval": curr, "regression": reg})
    assert "### Đánh giá ổn định (pass^k) & Trajectory" in md
    assert "### Kiểm định Regression" in md
    assert "KEEP" in md
    assert "Baseline" in md and "Current" in md and "Chênh lệch (Delta)" in md


def test_cli_agent_eval_with_baseline_and_regression(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    curr_dir = tmp_path / "curr"

    rc_base = eval_cli.main([
        "agent_eval",
        "--k",
        "2",
        "--threshold",
        "0.8",
        "--scenarios",
        "norm_place_search,oos_prompt_injection",
        "--out",
        str(base_dir),
    ])
    assert rc_base == 0
    assert (base_dir / "results.json").exists()
    assert (base_dir / "report.md").exists()

    rc_curr = eval_cli.main([
        "agent_eval",
        "--k",
        "2",
        "--threshold",
        "0.8",
        "--scenarios",
        "norm_place_search,oos_prompt_injection",
        "--baseline",
        str(base_dir / "results.json"),
        "--out",
        str(curr_dir),
    ])
    assert rc_curr == 0

    curr_json = json.loads((curr_dir / "results.json").read_text(encoding="utf-8"))
    curr_md = (curr_dir / "report.md").read_text(encoding="utf-8")
    assert "agent_eval" in curr_json
    assert "regression" in curr_json
    assert curr_json["regression"]["decision"] == "KEEP"
    assert "### Đánh giá ổn định (pass^k) & Trajectory" in curr_md
    assert "### Kiểm định Regression" in curr_md
