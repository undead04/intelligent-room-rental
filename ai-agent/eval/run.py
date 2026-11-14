"""CLI: python -m eval.run guardrail grounding [--llm] [--ablation] [--out eval_results]

  guardrail, grounding     : chạy ngay, tất định, không cần LLM/backend
  nlu                      : đo NLU bằng LLM thật (llm.get_llm("fast")) khi truyền --llm
  e2e / ablation           : cần hệ thống thật (default_deps: backend + LLM); chạy kịch bản và so sánh các cấu hình
  agent_eval               : chạy Eval Set lặp k lần (pass^k), chấm Trajectory + DoD và kiểm định Regression (--baseline)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument(
        "suites",
        nargs="*",
        default=["guardrail", "grounding"],
        choices=["guardrail", "grounding", "nlu", "e2e", "ablation", "agent_eval"],
    )
    ap.add_argument("--llm", action="store_true", help="NLU: đo bằng LLM thật")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="eval_results")
    ap.add_argument("--scenarios", default="", help="lọc kịch bản / case_id theo tên, phân tách bằng dấu phẩy")
    ap.add_argument("--k", type=int, default=3, help="số lần chạy lặp mỗi case cho agent_eval (pass^k)")
    ap.add_argument("--threshold", type=float, default=0.85, help="ngưỡng pass_all_k_rate công bố trước khi chạy agent_eval")
    ap.add_argument("--baseline", default="", help="đường dẫn file results.json của baseline để chạy kiểm định Regression")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)

    from eval import report

    results: dict[str, Any] = {}
    if "guardrail" in args.suites:
        from eval.suites import guardrail
        results["guardrail"] = guardrail.run()
    if "grounding" in args.suites:
        from eval.suites import grounding
        results["grounding"] = grounding.run(args.seed)
    if "nlu" in args.suites:
        if args.llm:
            from core.llm import get_llm
            from eval.suites import nlu
            model = get_llm("fast")
            if model is None:
                print("Không có LLM (kiểm tra cấu hình) - bỏ qua NLU bằng LLM", file=sys.stderr)
            else:
                results["nlu"] = {"llm": nlu.run_llm(model)}
        else:
            print("Bộ đo NLU cần LLM thật (thêm --llm để chạy).", file=sys.stderr)
    if "e2e" in args.suites or "ablation" in args.suites:
        from eval.datasets.scenarios import SCENARIOS
        from eval.suites import e2e
        from graph import default_deps
        picked = [s for s in SCENARIOS if not args.scenarios or s.name in args.scenarios.split(",")]
        if "ablation" in args.suites:
            results["ablation"] = e2e.run_ablation(default_deps, picked)
        else:
            results["e2e"] = e2e.run_scenarios(default_deps, picked)
    if "agent_eval" in args.suites:
        from eval.datasets.agent_eval_set import AGENT_EVAL_CASES
        from eval.stability_and_regression import compare_regression, run_repeated_eval

        picked_ids = {s.strip() for s in args.scenarios.split(",") if s.strip()} if args.scenarios else set()
        picked_cases = [c for c in AGENT_EVAL_CASES if not picked_ids or c.case_id in picked_ids]
        results["agent_eval"] = run_repeated_eval(picked_cases, k=args.k, pass_threshold=args.threshold)
        if args.baseline:
            raw_base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
            base_eval = raw_base["agent_eval"] if isinstance(raw_base, dict) and "agent_eval" in raw_base else raw_base
            results["regression"] = compare_regression(base_eval, results["agent_eval"], pass_threshold=args.threshold)
    j, m = report.save(results, args.out)
    print(f"Đã ghi {j} và {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
