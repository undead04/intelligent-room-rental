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


def ablation_md(res: dict[str, dict]) -> str:
    names = list(res)
    keys = [
        ("Tỉ lệ kiểm tra đạt", lambda s: fmt_rate(s["check_pass"])),
        ("Lượt có phòng bị cờ lỗi ở lần viết đầu", lambda s: fmt_rate(s["first_pass_flagged_rate"])),
        ("Lỗi tới tay người dùng", lambda s: fmt_rate(s["reached_user_flagged_rate"])),
        ("Phải dùng câu trả lời mẫu", lambda s: fmt_rate(s["fallback_template_rate"])),
        ("NLU rơi xuống keyword", lambda s: fmt_rate(s["nlu_fallback_rate"])),
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
    return "\n\n".join(parts) + "\n"


def save(results: dict[str, Any], out_dir: str) -> tuple[Path, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    j, m = d / "results.json", d / "report.md"
    j.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    m.write_text(build_report(results), encoding="utf-8")
    return j, m
