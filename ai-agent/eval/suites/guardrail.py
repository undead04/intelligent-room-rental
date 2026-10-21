from __future__ import annotations

from collections import defaultdict
from typing import Callable

from eval.baselines import old_guardrail
from eval.datasets.guardrail import build
from eval.metrics import rate
from safety.guardrails import check_guardrails

SYSTEMS: dict[str, Callable[[str], bool]] = {          # trả True nếu ĐƯỢC PHÉP đi tiếp
    "old": lambda t: old_guardrail(t)[0],
    "new": lambda t: check_guardrails(t).allowed,
}


def run(systems: dict[str, Callable[[str], bool]] | None = None) -> dict:
    cases = build()
    out: dict = {"n_cases": len(cases), "systems": {}}
    for name, allowed in (systems or SYSTEMS).items():
        attacks = [c for c in cases if c["label"] == "attack"]
        core = [c for c in attacks if c["category"] != "hard"]
        benign = [c for c in cases if c["label"] == "benign"]
        off = [c for c in cases if c["label"] == "offtopic"]
        blocked = {id(c): not allowed(c["text"]) for c in cases}
        by_cat: dict[str, list[bool]] = defaultdict(list)
        for c in attacks:
            by_cat[c["category"]].append(blocked[id(c)])
        out["systems"][name] = {
            "attack_recall_all": rate(sum(blocked[id(c)] for c in attacks), len(attacks)),
            "attack_recall_excl_hard": rate(sum(blocked[id(c)] for c in core), len(core)),
            "by_category": {k: rate(sum(v), len(v)) for k, v in sorted(by_cat.items())},
            "benign_false_positive": rate(sum(blocked[id(c)] for c in benign), len(benign)),
            "offtopic_blocked": rate(sum(blocked[id(c)] for c in off), len(off)),
            "false_positives": [c["text"] for c in benign if blocked[id(c)]],
            "missed_attacks": [c["text"] for c in attacks if not blocked[id(c)]][:25],
            "offtopic_passed": [c["text"] for c in off if not blocked[id(c)]],
        }
    return out
