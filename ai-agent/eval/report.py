from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.metrics import fmt_rate

CAVEAT = """> **Cách đọc các số đo.** Dataset do người viết hệ thống tạo và bám theo các luật/định dạng mà hệ thống mới xử lý, nên điểm của bản mới ở các bộ
> *tự tạo* là **cận trên lạc quan** (vòng tròn), không phải khả năng tổng quát hoá. Phần đáng tin là: (1) lỗi *cấu trúc* của bản cũ (không bỏ dấu, không nhận
> ký tự ẩn, không nhận bằng chứng từ công cụ, không hiểu 'k'/'đ'/diện tích), (2) nhóm HARD và các ca còn sót, (3) so sánh giữa các cấu hình trên *cùng* dữ liệu.
> Muốn số công bố được cần tập thử độc lập (câu thật từ log) và gán nhãn bởi người khác."""


def _table(rows: list[list[str]], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def guardrail_md(res: dict) -> str:
    sys_ = res["systems"]
    names = list(sys_)
    rows = [
        ["Recall tấn công (trừ nhóm HARD)"] + [fmt_rate(sys_[n]["attack_recall_excl_hard"]) for n in names],
        ["Recall tấn công (cả nhóm HARD)"] + [fmt_rate(sys_[n]["attack_recall_all"]) for n in names],
        ["Chặn nhầm câu hợp lệ"] + [fmt_rate(sys_[n]["benign_false_positive"]) for n in names],
        ["Off-topic bị chặn (bản mới để cho NLU xử lý)"] + [fmt_rate(sys_[n]["offtopic_blocked"]) for n in names],
    ]
    cats = sorted({c for n in names for c in sys_[n]["by_category"]})
    cat_rows = [[c] + [f"{sys_[n]['by_category'][c]['rate'] * 100:.0f}% ({sys_[n]['by_category'][c]['k']}/{sys_[n]['by_category'][c]['n']})" for n in names] for c in cats]
    md = f"### Guardrail ({res['n_cases']} ca)\n\n" + _table(rows, ["Chỉ số"] + names) + "\n\nRecall theo nhóm biến đổi:\n\n" + _table(cat_rows, ["Nhóm"] + names)
    for n in names:
        if sys_[n]["false_positives"]:
            md += f"\n\nChặn nhầm ({n}): " + "; ".join(f"“{t}”" for t in sys_[n]["false_positives"])
        if sys_[n]["missed_attacks"] and n == names[-1]:
            md += f"\n\nCòn sót ({n}): " + "; ".join(f"“{t}”" for t in sys_[n]["missed_attacks"][:8])
    return md


def grounding_md(res: dict) -> str:
    sys_ = res["systems"]
    names = list(sys_)
    rows = [
        ["Gắn cờ nhầm câu sạch (tất cả)"] + [fmt_rate(sys_[n]["clean_false_positive"]) for n in names],
        ["…câu sạch có số liệu từ công cụ"] + [fmt_rate(sys_[n]["clean_false_positive_with_tool"]) for n in names],
        ["…câu sạch không dùng công cụ"] + [fmt_rate(sys_[n]["clean_false_positive_plain"]) for n in names],
        ["Phát hiện lỗi tiêm vào (tất cả)"] + [fmt_rate(sys_[n]["detection_overall"]) for n in names],
    ]
    muts = sorted({m for n in names for m in sys_[n]["detection_by_mutation"]})
    mrows = [[m] + [fmt_rate(sys_[n]["detection_by_mutation"][m]) for n in names] for m in muts]
    return (f"### Kiểm chứng câu trả lời ({res['n_cases']} ca tổng hợp, seed {res['seed']})\n\n" + _table(rows, ["Chỉ số"] + names)
            + "\n\nPhát hiện theo loại lỗi:\n\n" + _table(mrows, ["Loại lỗi tiêm"] + names))


def nlu_md(results: dict[str, dict]) -> str:
    names = list(results)
    fields = sorted({f for r in results.values() for f in r["per_field"]})
    rows = [["Khớp hoàn toàn cả ca"] + [fmt_rate(results[n]["exact_match"]) for n in names]]
    rows += [[f] + [fmt_rate(results[n]["per_field"][f]) if f in results[n]["per_field"] else "-" for n in names] for f in fields]
    n_cases = next(iter(results.values()))["n_cases"]
    md = f"### NLU ({n_cases} ca vàng)\n\n" + _table(rows, ["Trường"] + names)
    first = results[names[0]]["failures"][:10]
    if first:
        md += f"\n\nVí dụ sai ({names[0]}):\n" + "\n".join(f"- “{f['text']}” → {f.get('field', '')}: kỳ vọng {f.get('expected')}, nhận {f.get('got', f.get('error'))}" for f in first)
    return md


def _fmt_pct(val: Any) -> str:
    return "N/A" if val is None else f"{float(val) * 100:.1f}%"


def _fmt_delta(val: Any) -> str:
    return "N/A" if val is None else f"{float(val) * 100:+.1f}%"


def agent_eval_md(res: dict) -> str:
    """Định dạng báo cáo đánh giá ổn định pass^k, DoD và Trajectory."""
    decl = res.get("pre_run_declaration") or {}
    s = res.get("summary") or {}
    versions = res.get("versions") or {}
    ver_str = ", ".join(f"{k}={v}" for k, v in sorted(versions.items())) if versions else "chưa gắn"
    rows = [
        ["Tỉ lệ đạt toàn bộ k lần (pass^k)", fmt_rate(s["pass_all_k_rate"])],
        ["Tỉ lệ đạt trung bình trên từng lượt", fmt_rate(s["mean_pass_rate"])],
        ["Tỉ lệ đạt Trajectory", fmt_rate(s["trajectory_pass_rate"])],
        ["Đủ bước bắt buộc (Trajectory Q1)", fmt_rate(s["sufficient_steps_rate"])],
        ["Không bước cấm/thừa (Trajectory Q2)", fmt_rate(s["no_forbidden_or_redundant_rate"])],
        ["Tỉ lệ đạt DoD Verifier", fmt_rate(s["dod_pass_rate"])],
        ["Số case không ổn định", str(s.get("unstable_case_count", 0))],
        ["Đạt ngưỡng công bố", "ĐẠT" if s.get("meets_threshold") else "KHÔNG ĐẠT"],
    ]
    header_info = (
        f"### Đánh giá ổn định (pass^k) & Trajectory\n\n"
        f"- **Khai báo trước khi chạy:** `k={decl.get('k')}`, ngưỡng đạt `{_fmt_pct(decl.get('pass_threshold'))}`\n"
        f"- **Eval set:** `{res.get('dataset_version')}` (digest `{res.get('dataset_digest')}`, {decl.get('n_cases')} cases)\n"
        f"- **Phiên bản trace:** `{ver_str}`\n\n"
    )
    parts = [header_info + _table(rows, ["Chỉ số", "Kết quả"])]

    unstable = res.get("unstable_cases") or []
    if unstable:
        lines = ["#### Danh sách case không ổn định & bước khác biệt đầu tiên\n"]
        for u in unstable:
            div = u.get("first_divergence") or {}
            run_ids = ", ".join(str(r) for r in (u.get("run_ids") or []))
            if div.get("diverged"):
                div_desc = (
                    f"bước `{div.get('first_diff_index')}` (`{div.get('step_type')}`, "
                    f"run `{div.get('run_id_a')}` seq `{div.get('seq_a')}` vs "
                    f"run `{div.get('run_id_b')}` seq `{div.get('seq_b')}`, "
                    f"trường lệch: `{', '.join(div.get('diff_fields') or [])}`)"
                )
            else:
                div_desc = "không phát hiện bước lệch cụ thể trong trace"
            lines.append(
                f"- **{u['case_id']}** ({u.get('pass_count')}/{u.get('k')} đạt, runs=[{run_ids}]): khác biệt đầu tiên tại {div_desc}."
            )
        parts.append("\n".join(lines))
    else:
        parts.append("Không có case không ổn định.")
    return "\n\n".join(parts)


def regression_md(reg: dict) -> str:
    """Định dạng bảng so sánh Regression (Baseline / Current / Delta) và kết luận KEEP/REJECT."""
    changed = reg.get("changed_versions") or {}
    changed_desc = (
        ", ".join(f"`{k}`: `{v.get('baseline')}` -> `{v.get('current')}`" for k, v in sorted(changed.items()))
        if changed
        else "Không ghi nhận khác biệt phiên bản prompt/skill/model"
    )
    metric_labels = {
        "pass_all_k_rate": "Tỉ lệ đạt cả k lần (pass^k)",
        "mean_pass_rate": "Tỉ lệ đạt trung bình",
        "trajectory_pass_rate": "Tỉ lệ đạt Trajectory",
        "sufficient_steps_rate": "Đủ bước bắt buộc (Q1)",
        "no_forbidden_or_redundant_rate": "Không bước cấm/thừa (Q2)",
        "dod_pass_rate": "Tỉ lệ đạt DoD Verifier",
    }
    comp = reg.get("metrics_comparison") or {}
    rows = [
        [
            metric_labels.get(k, k),
            _fmt_pct(comp[k].get("baseline")),
            _fmt_pct(comp[k].get("current")),
            _fmt_delta(comp[k].get("delta")),
        ]
        for k in comp
    ]
    regressed = reg.get("regressed_cases") or []
    improved = reg.get("improved_cases") or []
    reg_str = ", ".join(c["case_id"] for c in regressed) if regressed else "Không có"
    imp_str = ", ".join(c["case_id"] for c in improved) if improved else "Không có"

    return "\n\n".join([
        f"### Kiểm định Regression\n\n"
        f"- **Eval set khóa digest:** `{reg.get('dataset_version')}` (`{reg.get('dataset_digest')}`)\n"
        f"- **Thay đổi phiên bản:** {changed_desc}",
        _table(rows, ["Chỉ số", "Baseline", "Current", "Chênh lệch (Delta)"]),
        f"- **Case chuyển từ Đạt -> Rớt ({len(regressed)}):** {reg_str}\n"
        f"- **Case chuyển từ Rớt -> Đạt ({len(improved)}):** {imp_str}\n"
        f"- **Kết luận ({reg.get('decision')}):** {reg.get('decision_rationale')}",
    ])


def ablation_md(res: dict[str, dict]) -> str:
    names = list(res)
    keys = [
        ("Tỉ lệ kiểm tra đạt", lambda s: fmt_rate(s["check_pass"])),
        ("Lượt có phòng bị cờ lỗi ở lần viết đầu", lambda s: fmt_rate(s["first_pass_flagged_rate"])),
        ("Lỗi tới tay người dùng", lambda s: fmt_rate(s["reached_user_flagged_rate"])),
        ("Phải dùng câu trả lời mẫu", lambda s: fmt_rate(s["fallback_template_rate"])),
        ("Số lời gọi LLM / lượt (TB)", lambda s: f"{s['llm_calls_per_turn']['mean']:.2f}"),
        ("Token ước lượng / lượt (TB)", lambda s: f"{s['est_tokens_per_turn']['mean']:.0f}"),
        ("Độ trễ p50 / p95 (s)", lambda s: f"{s['latency_s']['p50']:.2f} / {s['latency_s']['p95']:.2f}"),
        ("Lượt lỗi hệ thống", lambda s: str(s["errors"])),
    ]
    rows = [[label] + [fn(res[n]["summary"]) for n in names] for label, fn in keys]
    return "### Ablation end-to-end\n\n" + _table(rows, ["Chỉ số"] + names)


def build_report(results: dict[str, Any]) -> str:
    parts = ["# Kết quả đánh giá Homigo\n", CAVEAT, ""]
    if "guardrail" in results:
        parts.append(guardrail_md(results["guardrail"]))
    if "grounding" in results:
        parts.append(grounding_md(results["grounding"]))
    if "nlu" in results:
        parts.append(nlu_md(results["nlu"]))
    if "ablation" in results:
        parts.append(ablation_md(results["ablation"]))
    if "agent_eval" in results:
        parts.append(agent_eval_md(results["agent_eval"]))
    if "regression" in results:
        parts.append(regression_md(results["regression"]))
    return "\n\n".join(parts) + "\n"


def save(results: dict[str, Any], out_dir: str) -> tuple[Path, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    j, m = d / "results.json", d / "report.md"
    j.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    m.write_text(build_report(results), encoding="utf-8")
    return j, m
