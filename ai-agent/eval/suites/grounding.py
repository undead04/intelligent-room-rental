from __future__ import annotations

from collections import defaultdict
from typing import Callable

from eval.baselines import old_verify_answer
from eval.datasets.grounding import GroundingCase, generate
from eval.metrics import rate
from safety.grounding import verify_answer_grounding

# trả True nếu câu trả lời BỊ GẮN CỜ (có lỗi)
Checker = Callable[[GroundingCase], bool]
SYSTEMS: dict[str, Checker] = {
    "old": lambda c: not old_verify_answer(c.answer, c.rooms, c.pref)[0],                       # không nhận bằng chứng từ công cụ
    "new": lambda c: not verify_answer_grounding(c.answer, c.rooms, c.pref, extra_texts=c.evidence).is_grounded,
}


def run(seed: int = 7, systems: dict[str, Checker] | None = None) -> dict:
    cases = generate(seed)
    out: dict = {"seed": seed, "n_cases": len(cases), "systems": {}}
    for name, flagged in (systems or SYSTEMS).items():
        flags = [flagged(c) for c in cases]
        clean = [(c, f) for c, f in zip(cases, flags) if c.label == "clean"]
        det: dict[str, list[bool]] = defaultdict(list)
        for c, f in zip(cases, flags):
            if c.label == "hallucinated":
                det[c.mutation].append(f)
        hall = [f for c, f in zip(cases, flags) if c.label == "hallucinated"]
        out["systems"][name] = {
            "clean_false_positive": rate(sum(f for _, f in clean), len(clean)),
            "clean_false_positive_with_tool": rate(sum(f for c, f in clean if c.clean_kind == "with_tool"), sum(1 for c, _ in clean if c.clean_kind == "with_tool")),
            "clean_false_positive_plain": rate(sum(f for c, f in clean if c.clean_kind == "plain"), sum(1 for c, _ in clean if c.clean_kind == "plain")),
            "detection_overall": rate(sum(hall), len(hall)),
            "detection_by_mutation": {k: rate(sum(v), len(v)) for k, v in sorted(det.items())},
        }
    return out
