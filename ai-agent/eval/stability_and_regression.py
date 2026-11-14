"""Thực thi Eval Set theo k lần chạy (pass^k), phát hiện case bất ổn định, Trace Diff và kiểm định Regression.

Đáp ứng 4 trụ cột chuẩn đánh giá Agent:
  1. Eval Set bất biến (`compute_eval_set_digest`): khóa chặt bộ case giữa hai phiên bản so sánh.
  2. Chạy lặp k lần: công bố `k` và `pass_threshold` trước khi chạy; báo tỉ lệ `pass_all_k_rate`
     cùng danh sách `unstable_cases` và bước đầu tiên 2 trace khác nhau (`diff_traces_first_divergence`).
  3. Chấm Trajectory: dùng `eval.trajectory.grade_trajectory` cho từng lượt chạy.
  4. Regression Gate: bảng Baseline / Current / Delta từng chỉ số, danh sách case Đạt -> Rớt / Rớt -> Đạt,
     bắt buộc REJECT nếu có case Đạt -> Rớt kể cả khi chỉ số tổng không giảm, và quy chênh lệch về phiên bản
     `prompt` / `skill` / `model` gắn trong trace.
"""

from __future__ import annotations

import copy
import json
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional, Sequence

from core.session_store import SessionStore
from eval.datasets.agent_eval_set import (
    AGENT_EVAL_CASES,
    EVAL_SET_VERSION,
    EvalCase,
    compute_eval_set_digest,
)
from eval.metrics import rate
from eval.trajectory import grade_trajectory
from graph import Deps, build_housing_graph, run_turn
from graph.nodes.clarification import ClarifyReply
from graph.tracing import TraceStore
from intelligence.advice import Advice, ZeroResultAdvice
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from langchain_core.messages import AIMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers dựng môi trường giả lập nhất quán theo InitialSystemState + FaultInjection
# ---------------------------------------------------------------------------

_EVAL_CITIES = [
    {"id": 79, "name": "Thành phố Hồ Chí Minh"},
    {"id": 1, "name": "Thành phố Hà Nội"},
    {"id": 74, "name": "Tỉnh Bình Dương"},
]
_EVAL_DISTRICTS = [
    {"id": 784, "city_id": 79, "name": "Thành phố Thủ Đức"},
    {"id": 778, "city_id": 79, "name": "Quận 7"},
    {"id": 760, "city_id": 79, "name": "Quận 1"},
    {"id": 761, "city_id": 79, "name": "Quận 10"},
    {"id": 764, "city_id": 79, "name": "Quận Gò Vấp"},
    {"id": 724, "city_id": 74, "name": "Thành phố Dĩ An"},
]
_EVAL_WARDS = [
    {"id": 1001, "district_id": 784, "name": "Phường Linh Trung"},
    {"id": 1002, "district_id": 784, "name": "Phường Linh Xuân"},
]


class _EvalAdminDB:
    """AdminLookup chuẩn phục vụ chạy Eval Set (trả cấu trúc thành phố/quận/phường Việt Nam)."""

    def __call__(self, level: str, name: str, city_id: Optional[int] = None, district_id: Optional[int] = None):
        from tools.location_service import admin_key
        from utils.text import norm_key

        rows = {"city": _EVAL_CITIES, "district": _EVAL_DISTRICTS, "ward": _EVAL_WARDS}[level]
        out = [r for r in rows if norm_key(name) in norm_key(r["name"]) or admin_key(name) in norm_key(r["name"])]
        if city_id is not None and level == "district":
            out = [r for r in out if r["city_id"] == city_id]
        if district_id is not None and level == "ward":
            out = [r for r in out if r["district_id"] == district_id]
        return out


class _ScriptedBoundLLM:
    def __init__(self, llm: "_ScriptedLLM", schema_name: str):
        self.llm = llm
        self.schema_name = schema_name

    def invoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        return self.llm._next(self.schema_name, messages)


class _ScriptedLLM:
    """FakeLLM theo kịch bản cấu trúc từng Schema cho EvalCase."""

    def __init__(self, queues: dict[str, list[Any]]):
        self.queues = {k: list(v) for k, v in queues.items()}

    def _next(self, schema_name: str, messages: Any) -> Any:
        q = self.queues.get(schema_name)
        if not q:
            raise RuntimeError(f"_ScriptedLLM thiếu cấu hình đầu ra cho schema '{schema_name}'")
        item = q.pop(0) if len(q) > 1 else q[0]
        return item(messages) if callable(item) else item

    def with_structured_output(self, schema: Any, **kw: Any) -> _ScriptedBoundLLM:
        return _ScriptedBoundLLM(self, getattr(schema, "__name__", str(schema)))

    def invoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(content=self._next("text", messages))


class _ScriptedAgent:
    """Fake ReAct agent cho luồng room_followup."""

    def __init__(self, replies: Sequence[dict[str, Any]]):
        self.replies = list(replies)

    def invoke(self, payload: dict[str, Any], config: Optional[dict] = None) -> dict[str, Any]:
        item = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        msgs = list(payload["messages"])
        if item.get("tool"):
            msgs.append(ToolMessage(content=str(item["tool"]), tool_call_id="call_detail_1"))
        msgs.append(AIMessage(content=str(item.get("text", ""))))
        return {"messages": msgs}


def _to_turn_analysis(raw: Mapping[str, Any]) -> TurnAnalysis:
    patch = PreferencePatch(**dict(raw.get("patch") or {}))
    priorities = Priorities(**dict(raw.get("priorities") or {}))
    return TurnAnalysis(
        intent=raw["intent"],
        skill_slug=raw.get("skill_slug"),
        referenced_room_rank=raw.get("referenced_room_rank"),
        is_multi_intent=bool(raw.get("is_multi_intent", False)),
        patch=patch,
        priorities=priorities,
        priority_reasons=list(raw.get("priority_reasons") or ()),
        reset_priorities=bool(raw.get("reset_priorities", False)),
        semantic_query=raw.get("semantic_query"),
    )


def _build_deps_for_case(
    case: EvalCase,
    *,
    run_index: int,
    deps_flags: Optional[Mapping[str, Any]] = None,
    versions_override: Optional[Mapping[str, str]] = None,
) -> Deps:
    unreliable_n = case.fault_injection.unreliable_llm_every_n
    inject_unreliable = unreliable_n > 0 and ((run_index + 1) % unreliable_n == 0)

    nlu_items = [_to_turn_analysis(item) for item in case.scripted_nlu]
    if inject_unreliable and nlu_items:
        # Giả lập NLU bất ổn ở đúng lượt lặp thứ N -> tạo khác biệt tại model_call
        nlu_items = [
            TurnAnalysis(intent="off_topic") if idx == len(nlu_items) - 1 else item
            for idx, item in enumerate(nlu_items)
        ]

    queues: dict[str, list[Any]] = {}
    if nlu_items:
        queues["TurnAnalysis"] = nlu_items
    if case.scripted_advice:
        queues["Advice"] = [Advice(**dict(a)) for a in case.scripted_advice]
    if case.scripted_zero_advice:
        queues["ZeroResultAdvice"] = [ZeroResultAdvice(**dict(z)) for z in case.scripted_zero_advice]
    if case.scripted_clarify:
        queues["ClarifyReply"] = [ClarifyReply(**dict(c)) for c in case.scripted_clarify]
    if case.scripted_text_replies:
        queues["text"] = list(case.scripted_text_replies)

    llm = _ScriptedLLM(queues) if queues else None
    sessions = SessionStore()

    def search_rooms(args: dict[str, Any]) -> dict[str, Any]:
        if case.fault_injection.search_error:
            raise RuntimeError(case.fault_injection.search_error)
        min_rad = case.initial_state.min_rooms_radius_km
        if min_rad is not None:
            rad = args.get("max_distance_km")
            if rad is not None and float(rad) < float(min_rad):
                return {"ok": True, "data": []}
        return {"ok": True, "data": [copy.deepcopy(r) for r in case.initial_state.rooms]}

    def geocode(q: str, hint: Optional[str]) -> Optional[dict[str, float]]:
        if case.fault_injection.geocode_error:
            raise RuntimeError(case.fault_injection.geocode_error)
        if not case.initial_state.geocode_place_ok:
            return None
        return {"lat": 10.87, "lng": 106.8}

    def consult_skill(slug: str, query: str) -> dict[str, Any]:
        return {
            "ok": True,
            "instructions": (
                "Hướng dẫn kiểm tra hợp đồng thuê trọ: luôn đối chiếu điều khoản tiền cọc, "
                "thời hạn báo trước, biên lai chuyển khoản và giữ chứng từ giao dịch."
            ),
            "references": {},
        }

    skill_obj = SimpleNamespace(
        slug="rental-contract-advisor",
        name="Rental Contract Advisor",
        description="Tư vấn hợp đồng, tiền cọc và quyền lợi người thuê trọ",
        follow_ups=["Mẫu biên bản bàn giao phòng"],
        triggers=["cọc", "hợp đồng"],
    )

    market_fetcher = None
    if case.initial_state.market_stats:
        ms = case.initial_state.market_stats
        min_p = ms.get("minimum_price_vnd", ms.get("min_price"))
        avg_p = ms.get("average_price_vnd", ms.get("avg_price"))
        tot = ms.get("total_listings", ms.get("count", 25))
        market_fetcher = lambda **kw: {
            "minimum_price_vnd": min_p,
            "average_price_vnd": avg_p,
            "total_listings": tot,
        }

    agent_factory = None
    if case.scripted_agent_replies:
        agent_factory = lambda: _ScriptedAgent(case.scripted_agent_replies)

    kwargs: dict[str, Any] = {}
    if versions_override:
        if "prompt" in versions_override:
            kwargs["prompt_version"] = str(versions_override["prompt"])
        if "skill" in versions_override:
            kwargs["skill_version"] = str(versions_override["skill"])
        if "model" in versions_override:
            kwargs["model_version"] = str(versions_override["model"])

    deps = Deps(
        sessions=sessions,
        get_llm=(lambda role: llm) if llm is not None else (lambda role: None),
        base_prompt="BASE_HOMIGO_EVAL",
        decision_system_prompt="DECISION_HOMIGO_EVAL",
        search_rooms=search_rooms,
        geocode=geocode,
        admin_lookup=_EvalAdminDB(),
        consult_skill=consult_skill,
        skills=lambda: {"rental-contract-advisor": skill_obj},
        market_fetcher=market_fetcher,
        decision_agent=agent_factory,
        enable_critic=False,
        verify_answers=True,
        max_answer_retries=2,
        **kwargs,
    )
    for k, v in (deps_flags or {}).items():
        if hasattr(deps, k):
            setattr(deps, k, v)
    return deps


def _check_preferences_subset(pref: Any, expected_subset: Mapping[str, Any]) -> list[str]:
    if not expected_subset:
        return []
    if pref is None:
        return ["current_preferences bị None dù có kỳ vọng expected_preferences_subset"]
    errors: list[str] = []
    for field_name, expected_val in expected_subset.items():
        actual_raw = getattr(pref, field_name, None)
        if isinstance(actual_raw, list):
            actual_val = [x.value if hasattr(x, "value") else x for x in actual_raw]
        elif hasattr(actual_raw, "value"):
            actual_val = actual_raw.value
        else:
            actual_val = actual_raw
        if actual_val != expected_val:
            errors.append(
                f"preference.{field_name} mong đợi {expected_val!r} nhưng nhận {actual_val!r}"
            )
    return errors


# ---------------------------------------------------------------------------
# Thực thi đơn lẻ 1 lượt/1 case & So sánh Trace tìm bước khác biệt đầu tiên
# ---------------------------------------------------------------------------

def evaluate_single_case_run(
    case: EvalCase,
    *,
    run_index: int = 0,
    versions_override: Optional[Mapping[str, str]] = None,
    deps_flags: Optional[Mapping[str, Any]] = None,
    runner_hook: Optional[Callable[[EvalCase, int, TraceStore], tuple[Any, list[str]]]] = None,
) -> dict[str, Any]:
    """Chạy 1 lượt trọn vẹn cho `case` với `run_id` độc lập và chấm Behavior + DoD + Trajectory."""
    run_id = f"run_{case.case_id}_{run_index + 1}_{uuid.uuid4().hex[:8]}"
    versions = {
        "prompt": str((versions_override or {}).get("prompt", "homigo-prompt-v2.0")),
        "skill": str((versions_override or {}).get("skill", "housing-skills-v1.0")),
        "model": str((versions_override or {}).get("model", "default")),
    }
    store = TraceStore(run_id=run_id, case_id=case.case_id, versions=versions)

    last_resp = None
    observed_intents: list[str] = []
    runtime_error: Optional[str] = None

    if runner_hook is not None:
        try:
            last_resp, observed_intents = runner_hook(case, run_index, store)
        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
    else:
        deps = _build_deps_for_case(
            case,
            run_index=run_index,
            deps_flags=deps_flags,
            versions_override=versions_override,
        )
        graph = build_housing_graph(deps)
        sid = f"eval-{case.case_id}"
        try:
            for turn_text in case.turns:
                last_resp = run_turn(
                    graph,
                    turn_text,
                    session_id=sid,
                    case_id=case.case_id,
                    trace_store=store,
                )
        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"

    spans = store.snapshot()
    if not observed_intents:
        for sp in spans:
            if sp.get("type") == "model_response" and sp.get("node") == "understand_node":
                out = sp.get("output")
                if isinstance(out, Mapping) and out.get("intent"):
                    observed_intents.append(str(out["intent"]))

    failure_reasons: list[str] = []
    if runtime_error is not None:
        failure_reasons.append(f"Lỗi runtime: {runtime_error}")

    # 1) Chấm trạng thái cuối & hành vi
    exp = case.expected
    state_ok = runtime_error is None and last_resp is not None
    if last_resp is not None:
        last_intent = observed_intents[-1] if observed_intents else ""
        if isinstance(exp.expected_intent, tuple):
            if exp.expected_intent and last_intent not in exp.expected_intent:
                state_ok = False
                failure_reasons.append(f"intent mong đợi thuộc {exp.expected_intent}, nhận '{last_intent}'")
            elif not exp.expected_intent and last_intent != "":
                state_ok = False
                failure_reasons.append(f"mong đợi chặn trước understand_node (intent rỗng), nhận '{last_intent}'")
        elif exp.expected_intent and last_intent != exp.expected_intent:
            state_ok = False
            failure_reasons.append(f"intent mong đợi '{exp.expected_intent}', nhận '{last_intent}'")

        n_rooms = len(getattr(last_resp, "rooms", ()) or ())
        if exp.min_rooms is not None and n_rooms < exp.min_rooms:
            state_ok = False
            failure_reasons.append(f"số phòng {n_rooms} < min_rooms={exp.min_rooms}")
        if exp.max_rooms is not None and n_rooms > exp.max_rooms:
            state_ok = False
            failure_reasons.append(f"số phòng {n_rooms} > max_rooms={exp.max_rooms}")

        need_clarify = bool(getattr(last_resp, "need_clarification", False))
        if exp.expect_clarification is not None and need_clarify is not exp.expect_clarification:
            state_ok = False
            failure_reasons.append(f"need_clarification={need_clarify}, mong đợi {exp.expect_clarification}")

        pref_errs = _check_preferences_subset(
            getattr(last_resp, "current_preferences", None),
            exp.expected_preferences_subset,
        )
        if pref_errs:
            state_ok = False
            failure_reasons.extend(pref_errs)

        reply_lower = str(getattr(last_resp, "text_reply", "") or "").lower()
        if exp.must_contain_any and not any(tok.lower() in reply_lower for tok in exp.must_contain_any):
            state_ok = False
            failure_reasons.append(f"câu trả lời thiếu ít nhất một từ khóa kỳ vọng {exp.must_contain_any}")
        for forbidden_txt in exp.must_not_contain:
            if forbidden_txt.lower() in reply_lower:
                state_ok = False
                failure_reasons.append(f"câu trả lời chứa nội dung cấm '{forbidden_txt}'")

    # 2) Chấm DoD Verifier (lấy trực tiếp từ verifier_decision span trong trace cô lập)
    verifier_spans = [sp for sp in spans if sp.get("type") == "verifier_decision"]
    last_verifier_passed: Optional[bool] = (
        bool(verifier_spans[-1].get("passed")) if verifier_spans else None
    )
    if exp.expect_verifier_passed is None:
        dod_ok = True
        dod_applicable = False
    else:
        dod_applicable = True
        dod_ok = last_verifier_passed is exp.expect_verifier_passed
        if not dod_ok:
            failure_reasons.append(
                f"DoD verifier passed={last_verifier_passed}, mong đợi {exp.expect_verifier_passed}"
            )

    # 3) Chấm Trajectory (từ Trace cô lập)
    traj_grade = grade_trajectory(spans, exp.trajectory)
    if not traj_grade.passed:
        if not traj_grade.gradable:
            failure_reasons.append(f"Trace không chấm được trajectory: {list(traj_grade.gradability_errors)}")
        if not traj_grade.sufficient_required_steps:
            failure_reasons.append(
                f"Trajectory thiếu bước/tham số bắt buộc: steps={list(traj_grade.missing_required_steps)}, args={list(traj_grade.missing_arg_details)}"
            )
        if not traj_grade.no_forbidden_or_redundant_steps:
            failure_reasons.append(
                f"Trajectory có bước cấm/thừa: forbidden={list(traj_grade.forbidden_violations)}, redundant={list(traj_grade.redundant_steps)}"
            )

    overall_passed = bool(state_ok and dod_ok and traj_grade.passed)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "run_index": run_index,
        "run_id": run_id,
        "versions": versions,
        "passed": overall_passed,
        "state_and_behavior_passed": state_ok,
        "dod_applicable": dod_applicable,
        "dod_passed": dod_ok,
        "trajectory_passed": traj_grade.passed,
        "trajectory_grade": traj_grade.to_dict(),
        "failure_reasons": failure_reasons,
        "trace_spans": spans,
    }


def _extract_comparable_steps(
    trace_events: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Optional[str], Optional[str], list[str]]:
    """Chuẩn hóa trace thành chuỗi bước (model_call, tool_call, verifier_decision) kèm kiểm metadata diff."""
    missing_meta: list[str] = []
    run_id: Optional[str] = None
    case_id: Optional[str] = None
    steps: list[dict[str, Any]] = []

    req_inputs_by_idx: dict[Any, Any] = {}
    for ev in trace_events:
        if run_id is None and ev.get("run_id"):
            run_id = str(ev["run_id"])
        if case_id is None and ev.get("case_id"):
            case_id = str(ev["case_id"])
        if ev.get("type") == "model_request":
            req_inputs_by_idx[ev.get("model_call_index")] = ev.get("input")

    if not run_id:
        missing_meta.append("run_id")
    if not case_id:
        missing_meta.append("case_id")

    for ev in sorted(trace_events, key=lambda s: int(s.get("seq") or 0)):
        t = ev.get("type")
        if t in ("model_response", "model_call"):
            inp = ev.get("input") if ev.get("input") is not None else req_inputs_by_idx.get(ev.get("model_call_index"))
            out = ev.get("output")
            if inp is None:
                missing_meta.append(f"seq={ev.get('seq')}:model_call.input")
            if out is None and ev.get("error") is None:
                missing_meta.append(f"seq={ev.get('seq')}:model_call.output")
            steps.append({
                "kind": "model_call",
                "seq": ev.get("seq"),
                "node": ev.get("node"),
                "input": inp,
                "output": out,
                "error": ev.get("error"),
            })
        elif t in ("tool_finished", "tool_call"):
            steps.append({
                "kind": "tool_call",
                "seq": ev.get("seq"),
                "node": ev.get("node"),
                "tool": ev.get("tool") or ev.get("tool_name"),
                "args": ev.get("args") if "args" in ev else ev.get("arguments"),
                "status": ev.get("status"),
                "result": ev.get("result"),
                "error": ev.get("error"),
            })
        elif t == "verifier_decision":
            steps.append({
                "kind": "verifier_decision",
                "seq": ev.get("seq"),
                "node": ev.get("node"),
                "passed": ev.get("passed"),
                "next_decision": ev.get("next_decision"),
                "failures": ev.get("failures"),
            })

    return steps, run_id, case_id, list(dict.fromkeys(missing_meta))


def diff_traces_first_divergence(
    trace_a: Sequence[Mapping[str, Any]],
    trace_b: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """So hai trace của hai lượt chạy và chỉ ra chính xác bước ĐẦU TIÊN hai lượt khác nhau."""
    steps_a, run_id_a, case_id_a, miss_a = _extract_comparable_steps(trace_a)
    steps_b, run_id_b, case_id_b, miss_b = _extract_comparable_steps(trace_b)
    missing_meta = list(dict.fromkeys([*miss_a, *miss_b]))
    eff_case_id = case_id_a or case_id_b

    limit = max(len(steps_a), len(steps_b))
    for idx in range(limit):
        sa = steps_a[idx] if idx < len(steps_a) else None
        sb = steps_b[idx] if idx < len(steps_b) else None
        if sa is None or sb is None:
            return {
                "diverged": True,
                "first_diff_index": idx,
                "case_id": eff_case_id,
                "run_id_a": run_id_a,
                "run_id_b": run_id_b,
                "seq_a": sa.get("seq") if sa else None,
                "seq_b": sb.get("seq") if sb else None,
                "step_type": (sa or sb).get("kind"),
                "diff_fields": ["step_missing"],
                "step_a": sa,
                "step_b": sb,
                "trace_metadata_complete": len(missing_meta) == 0,
                "missing_trace_metadata": missing_meta,
            }

        compare_keys = ("kind", "node", "tool", "args", "status", "input", "output", "result", "error", "passed", "next_decision")
        diff_fields = [
            key
            for key in compare_keys
            if json.dumps(sa.get(key), ensure_ascii=False, sort_keys=True, default=str)
            != json.dumps(sb.get(key), ensure_ascii=False, sort_keys=True, default=str)
        ]
        if diff_fields:
            return {
                "diverged": True,
                "first_diff_index": idx,
                "case_id": eff_case_id,
                "run_id_a": run_id_a,
                "run_id_b": run_id_b,
                "seq_a": sa.get("seq"),
                "seq_b": sb.get("seq"),
                "step_type": sa.get("kind"),
                "diff_fields": diff_fields,
                "step_a": sa,
                "step_b": sb,
                "trace_metadata_complete": len(missing_meta) == 0,
                "missing_trace_metadata": missing_meta,
            }

    return {
        "diverged": False,
        "first_diff_index": None,
        "case_id": eff_case_id,
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "trace_metadata_complete": len(missing_meta) == 0,
        "missing_trace_metadata": missing_meta,
    }


# ---------------------------------------------------------------------------
# Chạy lặp k lần (pass^k) & Tổng hợp kết quả
# ---------------------------------------------------------------------------

def _collect_trace_versions(runs: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    for r in runs:
        for sp in r.get("trace_spans") or ():
            vers = sp.get("versions")
            if isinstance(vers, Mapping) and vers:
                return {str(k): str(v) for k, v in vers.items()}
        vers = r.get("versions")
        if isinstance(vers, Mapping) and vers:
            return {str(k): str(v) for k, v in vers.items()}
    return {}


def run_repeated_eval(
    cases: Sequence[EvalCase] = AGENT_EVAL_CASES,
    *,
    k: int = 3,
    pass_threshold: float = 0.85,
    versions_override: Optional[Mapping[str, str]] = None,
    deps_flags: Optional[Mapping[str, Any]] = None,
    runner_hook: Optional[Callable[[EvalCase, int, TraceStore], tuple[Any, list[str]]]] = None,
) -> dict[str, Any]:
    """Chạy toàn bộ `cases` mỗi case `k` lần; công bố `k` và ngưỡng đạt trước khi thực thi."""
    if k < 1:
        raise ValueError("k phải >= 1")
    if not (0.0 <= pass_threshold <= 1.0):
        raise ValueError("pass_threshold phải nằm trong [0.0, 1.0]")

    dataset_digest = compute_eval_set_digest(cases)
    pre_run_declaration = {
        "k": int(k),
        "pass_threshold": float(pass_threshold),
        "dataset_version": EVAL_SET_VERSION,
        "dataset_digest": dataset_digest,
        "n_cases": len(cases),
        "declared_before_execution": True,
    }

    case_results: list[dict[str, Any]] = []
    unstable_cases: list[dict[str, Any]] = []
    all_runs: list[dict[str, Any]] = []

    pass_all_k_count = 0
    total_runs = 0
    total_passes = 0
    total_traj_pass = 0
    total_sufficient = 0
    total_no_forbidden = 0
    total_dod_applicable = 0
    total_dod_pass = 0

    for case in cases:
        runs_for_case = [
            evaluate_single_case_run(
                case,
                run_index=idx,
                versions_override=versions_override,
                deps_flags=deps_flags,
                runner_hook=runner_hook,
            )
            for idx in range(k)
        ]
        all_runs.extend(runs_for_case)

        pass_count = sum(1 for r in runs_for_case if r["passed"])
        passed_all_k = pass_count == k
        if passed_all_k:
            pass_all_k_count += 1

        for r in runs_for_case:
            total_runs += 1
            total_passes += int(r["passed"])
            total_traj_pass += int(r["trajectory_passed"])
            tg = r["trajectory_grade"]
            total_sufficient += int(bool(tg.get("sufficient_required_steps")))
            total_no_forbidden += int(bool(tg.get("no_forbidden_or_redundant_steps")))
            if r["dod_applicable"]:
                total_dod_applicable += 1
                total_dod_pass += int(r["dod_passed"])

        # Kiểm tra độ ổn định giữa k lần chạy (kết quả hoặc đường đi trace khác nhau)
        first_div: Optional[dict[str, Any]] = None
        if k >= 2:
            ref_run = next((r for r in runs_for_case if r["passed"]), runs_for_case[0])
            for cand in runs_for_case:
                if cand["run_id"] == ref_run["run_id"]:
                    continue
                if cand["passed"] != ref_run["passed"]:
                    first_div = diff_traces_first_divergence(ref_run["trace_spans"], cand["trace_spans"])
                    break
                d = diff_traces_first_divergence(ref_run["trace_spans"], cand["trace_spans"])
                if d.get("diverged"):
                    first_div = d
                    break

        is_unstable = (0 < pass_count < k) or (first_div is not None and bool(first_div.get("diverged")))
        if is_unstable:
            unstable_cases.append({
                "case_id": case.case_id,
                "category": case.category,
                "pass_count": pass_count,
                "k": k,
                "run_ids": [r["run_id"] for r in runs_for_case],
                "failure_reasons": sorted({msg for r in runs_for_case for msg in r["failure_reasons"]}),
                "first_divergence": first_div,
            })

        case_results.append({
            "case_id": case.case_id,
            "category": case.category,
            "target_requirements": list(case.target_requirements),
            "passed_all_k": passed_all_k,
            "pass_count": pass_count,
            "k": k,
            "unstable": is_unstable,
            "first_divergence": first_div,
            "failure_reasons": sorted({msg for r in runs_for_case for msg in r["failure_reasons"]}),
            "runs": [
                {
                    "run_index": r["run_index"],
                    "run_id": r["run_id"],
                    "versions": r["versions"],
                    "passed": r["passed"],
                    "state_and_behavior_passed": r["state_and_behavior_passed"],
                    "dod_passed": r["dod_passed"],
                    "trajectory_passed": r["trajectory_passed"],
                    "trajectory_grade": r["trajectory_grade"],
                    "failure_reasons": r["failure_reasons"],
                    "trace_spans": r["trace_spans"],
                }
                for r in runs_for_case
            ],
        })

    pass_all_k_rate = rate(pass_all_k_count, len(cases))
    summary = {
        "pass_all_k_rate": pass_all_k_rate,
        "mean_pass_rate": rate(total_passes, total_runs),
        "trajectory_pass_rate": rate(total_traj_pass, total_runs),
        "sufficient_steps_rate": rate(total_sufficient, total_runs),
        "no_forbidden_or_redundant_rate": rate(total_no_forbidden, total_runs),
        "dod_pass_rate": rate(total_dod_pass, total_dod_applicable),
        "unstable_case_count": len(unstable_cases),
        "meets_threshold": (pass_all_k_rate["rate"] or 0.0) >= pass_threshold,
    }

    return {
        "pre_run_declaration": pre_run_declaration,
        "dataset_version": EVAL_SET_VERSION,
        "dataset_digest": dataset_digest,
        "versions": _collect_trace_versions(all_runs),
        "summary": summary,
        "unstable_cases": unstable_cases,
        "cases": case_results,
    }


# ---------------------------------------------------------------------------
# Kiểm định Regression giữa Baseline và Current
# ---------------------------------------------------------------------------

def _extract_versions_from_eval_result(res: Mapping[str, Any]) -> dict[str, str]:
    top = res.get("versions")
    if isinstance(top, Mapping) and top:
        return {str(k): str(v) for k, v in top.items()}
    for c in res.get("cases") or ():
        for r in c.get("runs") or ():
            for sp in r.get("trace_spans") or ():
                if isinstance(sp.get("versions"), Mapping):
                    return {str(k): str(v) for k, v in sp["versions"].items()}
            if isinstance(r.get("versions"), Mapping):
                return {str(k): str(v) for k, v in r["versions"].items()}
    return {}


def compare_regression(
    baseline_result: Mapping[str, Any],
    current_result: Mapping[str, Any],
    *,
    pass_threshold: Optional[float] = None,
) -> dict[str, Any]:
    """So sánh kết quả cùng một Eval Set giữa baseline và phiên bản mới, khóa digest và ra quyết định KEEP/REJECT."""
    base_digest = baseline_result.get("dataset_digest")
    curr_digest = current_result.get("dataset_digest")
    if base_digest != curr_digest:
        raise ValueError(
            f"Eval set bị thay đổi giữa baseline ({base_digest}) và current ({curr_digest}); "
            "cần chạy lại cả hai trên cùng dataset_digest trước khi so sánh Regression."
        )

    base_cases = {c["case_id"]: c for c in (baseline_result.get("cases") or ())}
    curr_cases = {c["case_id"]: c for c in (current_result.get("cases") or ())}
    if set(base_cases.keys()) != set(curr_cases.keys()):
        raise ValueError("Danh sách case_id giữa baseline và current không trùng khớp.")

    # Quy chênh lệch về phiên bản prompt / skill / model từ trace
    base_versions = _extract_versions_from_eval_result(baseline_result)
    curr_versions = _extract_versions_from_eval_result(current_result)
    changed_versions: dict[str, dict[str, Optional[str]]] = {}
    for key in sorted(set(base_versions) | set(curr_versions)):
        bv = base_versions.get(key)
        cv = curr_versions.get(key)
        if bv != cv:
            changed_versions[key] = {"baseline": bv, "current": cv}

    # Bảng chỉ số Baseline / Current / Delta
    metric_names = (
        "pass_all_k_rate",
        "mean_pass_rate",
        "trajectory_pass_rate",
        "sufficient_steps_rate",
        "no_forbidden_or_redundant_rate",
        "dod_pass_rate",
    )
    base_sum = baseline_result.get("summary") or {}
    curr_sum = current_result.get("summary") or {}
    metrics_comparison: dict[str, dict[str, Optional[float]]] = {}
    for m in metric_names:
        b_rate = (base_sum.get(m) or {}).get("rate")
        c_rate = (curr_sum.get(m) or {}).get("rate")
        delta = round(float(c_rate) - float(b_rate), 4) if (b_rate is not None and c_rate is not None) else None
        metrics_comparison[m] = {"baseline": b_rate, "current": c_rate, "delta": delta}

    # Liệt kê chi tiết case chuyển Đạt -> Rớt và Rớt -> Đạt
    regressed_cases: list[dict[str, Any]] = []
    improved_cases: list[dict[str, Any]] = []
    unchanged_pass: list[str] = []
    unchanged_fail: list[str] = []

    for cid in sorted(base_cases.keys()):
        bc = base_cases[cid]
        cc = curr_cases[cid]
        b_ok = bool(bc.get("passed_all_k"))
        c_ok = bool(cc.get("passed_all_k"))
        if b_ok and not c_ok:
            regressed_cases.append({
                "case_id": cid,
                "category": cc.get("category"),
                "baseline_pass_count": bc.get("pass_count"),
                "current_pass_count": cc.get("pass_count"),
                "k": cc.get("k"),
                "current_failure_reasons": cc.get("failure_reasons") or [],
            })
        elif not b_ok and c_ok:
            improved_cases.append({
                "case_id": cid,
                "category": cc.get("category"),
                "baseline_pass_count": bc.get("pass_count"),
                "current_pass_count": cc.get("pass_count"),
                "k": cc.get("k"),
            })
        elif b_ok and c_ok:
            unchanged_pass.append(cid)
        else:
            unchanged_fail.append(cid)

    # Quy tắc kết luận Giữ hay Bỏ (nêu rõ chỉ số làm căn cứ)
    eff_threshold = (
        pass_threshold
        if pass_threshold is not None
        else float((current_result.get("pre_run_declaration") or {}).get("pass_threshold", 0.85))
    )
    pass_k_comp = metrics_comparison["pass_all_k_rate"]
    mean_comp = metrics_comparison["mean_pass_rate"]
    pass_k_curr = pass_k_comp["current"] if pass_k_comp["current"] is not None else 0.0
    pass_k_delta = pass_k_comp["delta"] if pass_k_comp["delta"] is not None else 0.0
    mean_delta = mean_comp["delta"] if mean_comp["delta"] is not None else 0.0

    basis_metrics = {
        "pass_all_k_rate": pass_k_comp,
        "mean_pass_rate": mean_comp,
        "trajectory_pass_rate": metrics_comparison["trajectory_pass_rate"],
        "dod_pass_rate": metrics_comparison["dod_pass_rate"],
        "pass_threshold": eff_threshold,
        "regressed_case_ids": [c["case_id"] for c in regressed_cases],
        "improved_case_ids": [c["case_id"] for c in improved_cases],
    }

    reasons: list[str] = []
    if regressed_cases:
        reasons.append(
            f"Có {len(regressed_cases)} case chuyển từ ĐẠT sang RỚT ({', '.join(c['case_id'] for c in regressed_cases)}) "
            f"— không được giữ thay đổi dù pass_all_k_rate={pass_k_curr:.2%} (delta={pass_k_delta:+.2%})."
        )
    if pass_k_curr < eff_threshold:
        reasons.append(f"pass_all_k_rate={pass_k_curr:.2%} thấp hơn ngưỡng công bố {eff_threshold:.2%}.")
    if pass_k_delta < 0:
        reasons.append(f"pass_all_k_rate giảm delta={pass_k_delta:+.2%}.")
    if mean_delta < 0:
        reasons.append(f"mean_pass_rate giảm delta={mean_delta:+.2%}.")

    if reasons:
        decision = "REJECT"
        decision_rationale = "BỎ THAY ĐỔI (REJECT): " + " ".join(reasons)
    else:
        decision = "KEEP"
        decision_rationale = (
            f"GIỮ THAY ĐỔI (KEEP): 0 case chuyển ĐẠT -> RỚT; "
            f"pass_all_k_rate={pass_k_curr:.2%} (delta={pass_k_delta:+.2%}, ngưỡng={eff_threshold:.2%}), "
            f"mean_pass_rate delta={mean_delta:+.2%}."
        )

    return {
        "dataset_version": current_result.get("dataset_version"),
        "dataset_digest": curr_digest,
        "baseline_versions": base_versions,
        "current_versions": curr_versions,
        "changed_versions": changed_versions,
        "metrics_comparison": metrics_comparison,
        "regressed_cases": regressed_cases,
        "improved_cases": improved_cases,
        "unchanged_pass_cases": unchanged_pass,
        "unchanged_fail_cases": unchanged_fail,
        "decision": decision,
        "decision_rationale": decision_rationale,
        "basis_metrics": basis_metrics,
    }
