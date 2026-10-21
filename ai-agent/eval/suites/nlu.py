from __future__ import annotations

import contextlib
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from eval.datasets.nlu import CASES
from eval.metrics import rate
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis, analyze_turn
from intelligence.nlu_fallback import legacy_analysis
from domain.schemas import UserPreferenceState
from utils.text import norm_key

Analyzer = Callable[[dict], Optional[TurnAnalysis]]

SKILL_MD = """---
name: Rental Contract Advisor
description: Tư vấn hợp đồng thuê trọ, tiền cọc, hoàn cọc, quyền lợi người thuê
triggers: [hợp đồng, đặt cọc, hoàn cọc, giữ cọc, cọc]
---
x
"""


def _pref(ctx: dict) -> UserPreferenceState:
    return UserPreferenceState(location_text=ctx.get("location_text"), max_price=ctx.get("max_price"), amenities=ctx.get("amenities") or [])


@contextlib.contextmanager
def eval_skills() -> Iterator[dict]:
    """Một skill hợp đồng cố định để hai bên (LLM/keyword) cùng điều kiện."""
    from skills import skills_discovery as sd

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "rental-contract-advisor").mkdir()
        (Path(d) / "rental-contract-advisor" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        old = sd.SKILL_DIRS
        sd.SKILL_DIRS = [Path(d)]
        sd.clear_cache()
        try:
            yield sd.discover_housing_skills()
        finally:
            sd.SKILL_DIRS = old
            sd.clear_cache()


def keyword_analyzer() -> Analyzer:
    """Đường dự phòng không LLM (nlu_fallback)."""
    def run(c: dict) -> TurnAnalysis:
        ctx = c["ctx"]
        return legacy_analysis(c["text"], has_rooms=ctx.get("n_rooms", 0) > 0, hitl_pending=ctx.get("hitl_pending", False),
                               has_history=bool(ctx.get("n_rooms") or ctx.get("hitl_pending")))
    return run


def llm_analyzer(model: Any, skills: dict) -> Analyzer:
    def run(c: dict) -> Optional[TurnAnalysis]:
        ctx = c["ctx"]
        n = ctx.get("n_rooms", 0)
        brief = "; ".join(f"Top {i}: Phòng {i}" for i in range(1, n + 1))
        return analyze_turn(model, c["text"], _pref(ctx), rooms_brief=brief, hitl_pending=ctx.get("hitl_pending", False), n_rooms=n, skills=skills)
    return run


def oracle_analyzer() -> Analyzer:
    """Trả đúng kỳ vọng: chỉ để kiểm chứng bộ đo (phải ra 100%)."""
    def run(c: dict) -> TurnAnalysis:
        e = c["expect"]
        intent = e.get("intent", "new_search")
        intent = sorted(intent)[0] if isinstance(intent, (set, frozenset)) else intent
        patch = PreferencePatch(
            location_text=e.get("location"), location_kind=e.get("location_kind"), location_is_vague=bool(e.get("vague")),
            vague_category=e.get("vague_category"), location_region=e.get("vague_region"),
            min_price=e.get("min_price"), max_price=e.get("max_price"), min_area=e.get("min_area"), max_area=e.get("max_area"),
            room_type=e.get("room_type"), room_types_exclude=list(e.get("room_types_exclude", [])),
            amenities_add=list(e.get("amenities_add", [])), amenities_remove=list(e.get("amenities_remove", [])), clear=list(e.get("clear", [])))
        return TurnAnalysis(intent=intent, hitl_action=e.get("hitl_action"), skill_slug=e.get("skill"), referenced_room_rank=e.get("rank"),
                            patch=patch, priorities=Priorities(**e.get("priorities", {})))
    return run


def _flat(a: TurnAnalysis) -> dict[str, Any]:
    p = a.patch
    return {
        "intent": a.intent, "max_price": p.max_price, "min_price": p.min_price, "min_area": p.min_area, "max_area": p.max_area,
        "location": norm_key(p.location_text), "location_kind": p.location_kind, "vague": p.location_is_vague,
        "vague_category": norm_key(p.vague_category), "vague_region": norm_key(p.location_region),
        "room_type": p.room_type.value if p.room_type else None, "room_types_exclude": {r.value for r in p.room_types_exclude},
        "amenities_add": {x.value for x in p.amenities_add}, "amenities_remove": {x.value for x in p.amenities_remove}, "clear": set(p.clear),
        "hitl_action": a.hitl_action.value if a.hitl_action else None, "skill": a.skill_slug, "rank": a.referenced_room_rank,
        "priorities": {k: v for k, v in a.priorities.model_dump().items() if v is not None},
    }


def _match(field: str, expected: Any, got: Any) -> bool:
    if field == "intent":
        return got in expected if isinstance(expected, (set, frozenset, list)) else got == expected
    if field in ("location", "vague_category", "vague_region"):
        return norm_key(expected) in (got or "")
    if field == "vague":
        return bool(got) == bool(expected)
    if field == "priorities":
        return all((got.get(k) in ("high", "very_high")) if v == "high" else got.get(k) == v for k, v in expected.items())
    return got == expected


def evaluate(analyzer: Analyzer, cases: Optional[list[dict]] = None) -> dict:
    cases = cases or CASES
    per_field: dict[str, list[bool]] = defaultdict(list)
    failures, exact, none_count = [], 0, 0
    for c in cases:
        a = analyzer(c)
        if a is None:
            none_count += 1
            for f in c["expect"]:
                per_field[f].append(False)
            failures.append({"text": c["text"], "error": "analyzer trả None (LLM lỗi?)"})
            continue
        got = _flat(a)
        ok_all = True
        for f, exp in c["expect"].items():
            ok = _match(f, exp, got.get(f))
            per_field[f].append(ok)
            if not ok:
                ok_all = False
                failures.append({"text": c["text"], "field": f, "expected": exp if not isinstance(exp, set) else sorted(exp), "got": got.get(f) if not isinstance(got.get(f), set) else sorted(got[f])})
        exact += ok_all
    return {"n_cases": len(cases), "exact_match": rate(exact, len(cases)), "none_results": none_count,
            "per_field": {f: rate(sum(v), len(v)) for f, v in sorted(per_field.items())}, "failures": failures}


def run_keyword_baseline() -> dict:
    with eval_skills():
        return evaluate(keyword_analyzer())


def run_llm(model: Any) -> dict:
    with eval_skills() as skills:
        return evaluate(llm_analyzer(model, skills))
