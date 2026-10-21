"""CLI: python -m eval.run guardrail grounding nlu [--llm] [--ablation] [--out eval_results]

  guardrail, grounding     : chạy ngay, tất định, không cần LLM/backend
  nlu                      : luôn chạy baseline keyword; thêm --llm để đo NLU bằng LLM thật (llm.get_llm("fast"))
  e2e / ablation           : cần hệ thống thật (default_deps: backend + LLM); chạy kịch bản và so sánh các cấu hình
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("suites", nargs="*", default=["guardrail", "grounding", "nlu"], choices=["guardrail", "grounding", "nlu", "e2e", "ablation"])
    ap.add_argument("--llm", action="store_true", help="NLU: đo thêm bằng LLM thật")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="eval_results")
    ap.add_argument("--scenarios", default="", help="lọc kịch bản theo tên, phân tách bằng dấu phẩy")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)          # guardrail/fallback ghi WARNING cho mỗi ca -> tắt khi đo

    from eval import report

    results: dict[str, Any] = {}
    if "guardrail" in args.suites:
        from eval.suites import guardrail
        results["guardrail"] = guardrail.run()
    if "grounding" in args.suites:
        from eval.suites import grounding
        results["grounding"] = grounding.run(args.seed)
    if "nlu" in args.suites:
        from eval.suites import nlu
        results["nlu"] = {"keyword_fallback": nlu.run_keyword_baseline()}
        if args.llm:
            from core.llm import get_llm
            model = get_llm("fast")
            if model is None:
                print("Không có LLM (kiểm tra cấu hình) - bỏ qua NLU bằng LLM", file=sys.stderr)
            else:
                results["nlu"]["llm"] = nlu.run_llm(model)
    if "e2e" in args.suites or "ablation" in args.suites:
        from eval.datasets.scenarios import SCENARIOS
        from eval.suites import e2e
        from graph import default_deps
        picked = [s for s in SCENARIOS if not args.scenarios or s.name in args.scenarios.split(",")]
        if "ablation" in args.suites:
            results["ablation"] = e2e.run_ablation(default_deps, picked)
        else:
            results["e2e"] = e2e.run_scenarios(default_deps, picked)
    j, m = report.save(results, args.out)
    print(f"Đã ghi {j} và {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
