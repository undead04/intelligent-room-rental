"""Chạy kịch bản end-to-end + ablation. Đếm lời gọi LLM/độ trễ bằng bao bọc quanh get_llm (ước lượng token = ký tự/4)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from eval.datasets.scenarios import SCENARIOS, Scenario
from eval.metrics import rate, summarize
from graph import Deps, build_housing_graph, run_turn

ABLATION_CONFIGS: dict[str, dict[str, Any]] = {
    "A_v2_baseline":      {"nlu_enabled": False, "constrained_generation": False, "verify_answers": False},
    "B_+NLU":             {"nlu_enabled": True,  "constrained_generation": False, "verify_answers": False},
    "C_+constrained":     {"nlu_enabled": True,  "constrained_generation": True,  "verify_answers": False},
    "D_+verify_no_retry": {"nlu_enabled": True,  "constrained_generation": True,  "verify_answers": True, "max_answer_retries": 0},
    "E_full":             {"nlu_enabled": True,  "constrained_generation": True,  "verify_answers": True, "max_answer_retries": 2},
}


@dataclass
class CallStats:
    calls: list[dict] = field(default_factory=list)

    def snapshot(self) -> int:
        return len(self.calls)

    def since(self, i: int) -> list[dict]:
        return self.calls[i:]


def _chars(messages: Any) -> int:
    try:
        return sum(len(m[1]) if isinstance(m, tuple) else len(getattr(m, "content", str(m)) or "") for m in messages)
    except TypeError:
        return len(str(messages))


class _CountingBound:
    def __init__(self, inner: Any, stats: CallStats, name: str):
        self.inner, self.stats, self.name = inner, stats, name

    def invoke(self, messages: Any, *a: Any, **k: Any) -> Any:
        t0 = time.perf_counter()
        err = None
        try:
            out = self.inner.invoke(messages, *a, **k)
        except Exception as e:
            err, out = e, None
            raise
        finally:
            out_chars = len(out.model_dump_json()) if hasattr(out, "model_dump_json") else len(str(getattr(out, "content", out) or ""))
            self.stats.calls.append({"name": self.name, "s": time.perf_counter() - t0, "in": _chars(messages), "out": out_chars, "error": err is not None})
        return out


class CountingLLM:
    def __init__(self, inner: Any, stats: CallStats):
        self.inner, self.stats = inner, stats

    def with_structured_output(self, schema: Any, **kw: Any) -> _CountingBound:
        return _CountingBound(self.inner.with_structured_output(schema, **kw), self.stats, getattr(schema, "__name__", "structured"))

    def invoke(self, messages: Any, *a: Any, **k: Any) -> Any:
        return _CountingBound(self.inner, self.stats, "text").invoke(messages, *a, **k)


def count_llm_calls(deps: Deps, stats: CallStats) -> Deps:
    inner = deps.get_llm
    deps.get_llm = lambda role: (CountingLLM(m, stats) if (m := inner(role)) is not None else None)
    return deps


def run_scenarios(make_deps: Callable[[], Deps], scenarios: Optional[list[Scenario]] = None, flags: Optional[dict[str, Any]] = None) -> dict:
    scenarios = scenarios or SCENARIOS
    turns: list[dict] = []
    for sc in scenarios:
        stats = CallStats()
        deps = count_llm_calls(make_deps(), stats)          # phiên mới cho mỗi kịch bản
        for k, v in (flags or {}).items():
            setattr(deps, k, v)
        graph = build_housing_graph(deps)
        sid = f"eval-{sc.name}"
        for i, turn in enumerate(sc.turns, 1):
            mark = stats.snapshot()
            t0 = time.perf_counter()
            try:
                resp, error = run_turn(graph, turn.text, session_id=sid, ui_action=turn.ui_action), None
            except Exception as e:                           # một lượt lỗi không làm hỏng cả đợt đo
                resp, error = None, f"{type(e).__name__}: {e}"
            dt = time.perf_counter() - t0
            calls = stats.since(mark)
            row: dict = {"scenario": sc.name, "turn": i, "latency_s": dt, "llm_calls": len(calls), "est_tokens": sum(c["in"] + c["out"] for c in calls) / 4,
                         "llm_errors": sum(c["error"] for c in calls), "error": error, "checks": {}, "tags": list(sc.tags)}
            if resp is not None:
                g = resp.grounding_report
                notes = (g.retry_notes if g else []) or []
                enforced = True if g is None or g.enforced is None else g.enforced
                issues = (g.issues if g else []) or []
                row.update({
                    "rooms": len(resp.rooms), "nlu_fallback": any(e.get("type") == "nlu_fallback" for e in resp.trace_events),
                    "first_pass_flagged": bool(notes) or (not enforced and bool(issues)), "reached_user_flagged": (not enforced) and bool(issues),
                    "answer_retries": (g.answer_retries or 0) if g else 0, "fallback_template": bool(g and g.fallback_template_used),
                    "groundedness": g.groundedness_score if g else None, "checked": g.checked if g else None,
                })
                for name, fn in turn.checks:
                    try:
                        row["checks"][name] = bool(fn(resp))
                    except Exception:
                        row["checks"][name] = False
            else:
                for name, _ in turn.checks:
                    row["checks"][name] = False
            turns.append(row)
    return {"flags": flags or {}, "turns": turns, "summary": summarize_turns(turns)}


def summarize_turns(turns: list[dict]) -> dict:
    ok = [t for t in turns if t.get("error") is None]
    checks = [v for t in turns for v in t["checks"].values()]
    with_rooms = [t for t in ok if t.get("rooms")]
    return {
        "turns": len(turns), "errors": len(turns) - len(ok),
        "check_pass": rate(sum(checks), len(checks)),
        "latency_s": summarize(t["latency_s"] for t in turns),
        "llm_calls_per_turn": summarize(t["llm_calls"] for t in turns),
        "est_tokens_per_turn": summarize(t["est_tokens"] for t in turns),
        "nlu_fallback_rate": rate(sum(t.get("nlu_fallback", False) for t in ok), len(ok)),
        "first_pass_flagged_rate": rate(sum(t.get("first_pass_flagged", False) for t in with_rooms), len(with_rooms)),
        "reached_user_flagged_rate": rate(sum(t.get("reached_user_flagged", False) for t in with_rooms), len(with_rooms)),
        "fallback_template_rate": rate(sum(t.get("fallback_template", False) for t in with_rooms), len(with_rooms)),
    }


def run_ablation(make_deps: Callable[[], Deps], scenarios: Optional[list[Scenario]] = None, configs: Optional[dict[str, dict[str, Any]]] = None) -> dict:
    return {name: run_scenarios(make_deps, scenarios, flags) for name, flags in (configs or ABLATION_CONFIGS).items()}
