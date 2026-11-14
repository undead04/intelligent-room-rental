"""Bộ chấm điểm Trajectory độc lập cho Homigo AI Agent.

Nguyên tắc thiết kế:
1. Chỉ chấm được khi trace ghi đủ 3 thông tin cho mọi tool call:
   - Thứ tự thực thi (`seq`, nguyên dương, tăng đúng thứ tự)
   - Tên tool (`tool` / `tool_name` khác rỗng)
   - Tham số gọi tool (`args` / `arguments` dạng Mapping)
   Thiếu bất kỳ trường nào -> `gradable=False`, từ chối chấm đạt.
2. Không ép một chuỗi bước cố định: mô tả quy trình đúng bằng tập bước bắt buộc
   (`required_tools`, `required_arg_keys`) và danh sách điều cấm (`forbidden_tools`, `allowed_tools`, `max_calls_per_tool`).
3. Tách riêng hai câu hỏi:
   - Đủ bước cần thiết chưa? (`sufficient_required_steps`)
   - Có bước bị cấm hoặc bước thừa không? (`no_forbidden_or_redundant_steps`)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from eval.datasets.agent_eval_set import TrajectorySpec


@dataclass(frozen=True)
class ExtractedToolCall:
    """Thông tin chuẩn hóa một lời gọi tool rút ra từ trace."""

    seq: int
    tool: str
    args: Mapping[str, Any]
    status: str = "ok"
    tool_call_id: Optional[str] = None
    node: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool,
            "args": dict(self.args),
            "status": self.status,
            "tool_call_id": self.tool_call_id,
            "node": self.node,
        }


@dataclass(frozen=True)
class TrajectoryGrade:
    """Kết quả chấm điểm quỹ đạo tách biệt rõ tính chấm được, đủ bước và không thừa/cấm."""

    passed: bool
    gradable: bool
    gradability_errors: tuple[str, ...] = ()
    sufficient_required_steps: bool = False
    missing_required_steps: tuple[str, ...] = ()
    missing_arg_details: tuple[str, ...] = ()
    no_forbidden_or_redundant_steps: bool = False
    forbidden_violations: tuple[str, ...] = ()
    redundant_steps: tuple[str, ...] = ()
    observed_sequence: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "gradable": self.gradable,
            "gradability_errors": list(self.gradability_errors),
            "sufficient_required_steps": self.sufficient_required_steps,
            "missing_required_steps": list(self.missing_required_steps),
            "missing_arg_details": list(self.missing_arg_details),
            "no_forbidden_or_redundant_steps": self.no_forbidden_or_redundant_steps,
            "forbidden_violations": list(self.forbidden_violations),
            "redundant_steps": list(self.redundant_steps),
            "observed_sequence": list(self.observed_sequence),
        }


def _get_tool_name(ev: Mapping[str, Any]) -> str:
    raw = ev.get("tool") or ev.get("tool_name") or ""
    return str(raw).strip()


def _get_tool_args(ev: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    if "args" in ev and isinstance(ev.get("args"), Mapping):
        return ev.get("args")
    if "arguments" in ev and isinstance(ev.get("arguments"), Mapping):
        return ev.get("arguments")
    return None


def validate_trace_gradable(trace_events: Sequence[Mapping[str, Any]]) -> tuple[bool, list[str]]:
    """Kiểm tra trace có đủ thứ tự (`seq`), tên tool và tham số (`args`) để chấm quỹ đạo hay không."""
    if not isinstance(trace_events, Sequence):
        return False, ["trace_events không phải danh sách hợp lệ"]

    problems: list[str] = []
    prev_seq: Optional[int] = None

    for idx, ev in enumerate(trace_events):
        if not isinstance(ev, Mapping):
            problems.append(f"span #{idx} không phải dict/Mapping")
            continue

        ev_type = ev.get("type")
        if ev_type not in ("tool_call", "tool_started", "tool_finished"):
            continue

        raw_seq = ev.get("seq")
        if not isinstance(raw_seq, int) or isinstance(raw_seq, bool) or raw_seq <= 0:
            problems.append(f"tool span #{idx} ({ev_type}) thiếu thứ tự seq hợp lệ")
        else:
            if prev_seq is not None and raw_seq <= prev_seq:
                problems.append(f"tool span #{idx} ({ev_type}) có seq={raw_seq} không tăng sau seq={prev_seq}")
            prev_seq = raw_seq

        tname = _get_tool_name(ev)
        if not tname:
            problems.append(f"tool span #{idx} (seq={raw_seq}) thiếu tên tool")

        args = _get_tool_args(ev)
        if args is None:
            problems.append(f"tool span #{idx} (tool={tname or '?'}, seq={raw_seq}) thiếu tham số args/arguments")

    return len(problems) == 0, problems


def extract_tool_calls(trace_events: Sequence[Mapping[str, Any]]) -> list[ExtractedToolCall]:
    """Rút trích danh sách tool call duy nhất theo đúng thứ tự `seq` tăng dần."""
    finished_by_id: dict[str, Mapping[str, Any]] = {}
    started_unmatched: list[Mapping[str, Any]] = []
    ordered: list[Mapping[str, Any]] = []

    for ev in trace_events:
        if ev.get("type") in ("tool_finished", "tool_call"):
            cid = ev.get("tool_call_id")
            if cid:
                finished_by_id[str(cid)] = ev
            ordered.append(ev)

    for ev in trace_events:
        if ev.get("type") == "tool_started":
            cid = ev.get("tool_call_id")
            if not cid or str(cid) not in finished_by_id:
                started_unmatched.append(ev)

    combined = [*ordered, *started_unmatched]
    combined.sort(key=lambda e: int(e.get("seq") or 0))

    calls: list[ExtractedToolCall] = []
    for ev in combined:
        calls.append(
            ExtractedToolCall(
                seq=int(ev.get("seq") or 0),
                tool=_get_tool_name(ev),
                args=dict(_get_tool_args(ev) or {}),
                status=str(ev.get("status") or ("started_only" if ev.get("type") == "tool_started" else "ok")),
                tool_call_id=str(ev.get("tool_call_id")) if ev.get("tool_call_id") else None,
                node=str(ev.get("node")) if ev.get("node") else None,
            )
        )
    return calls


def _canonical_args(args: Mapping[str, Any]) -> str:
    return json.dumps(dict(args), ensure_ascii=False, sort_keys=True, default=str)


def grade_trajectory(
    trace_events: Sequence[Mapping[str, Any]],
    spec: TrajectorySpec,
) -> TrajectoryGrade:
    """Chấm điểm quỹ đạo theo 2 trục độc lập: đủ bước bắt buộc & không có bước cấm/thừa."""
    gradable, gradability_errors = validate_trace_gradable(trace_events)
    if not gradable:
        return TrajectoryGrade(
            passed=False,
            gradable=False,
            gradability_errors=tuple(gradability_errors),
            sufficient_required_steps=False,
            no_forbidden_or_redundant_steps=False,
        )

    calls = extract_tool_calls(trace_events)
    called_tools = [c.tool for c in calls]
    called_set = set(called_tools)

    # Câu hỏi 1: Đã đủ bước bắt buộc & đủ tham số bắt buộc chưa? (không ép 1 thứ tự cứng)
    missing_steps = [t for t in spec.required_tools if t not in called_set]
    missing_arg_details: list[str] = []

    for tool_name, required_keys in (spec.required_arg_keys or {}).items():
        matching_calls = [c for c in calls if c.tool == tool_name]
        if not matching_calls:
            if tool_name not in missing_steps:
                missing_steps.append(tool_name)
            continue
        best_call = max(
            matching_calls,
            key=lambda mc: sum(
                1 for k in required_keys if k in mc.args and mc.args[k] is not None and str(mc.args[k]).strip() != ""
            ),
        )
        missing_keys = [
            k
            for k in required_keys
            if not (k in best_call.args and best_call.args[k] is not None and str(best_call.args[k]).strip() != "")
        ]
        for k in missing_keys:
            missing_arg_details.append(f"{tool_name}.{k}")

    sufficient = (len(missing_steps) == 0) and (len(missing_arg_details) == 0)

    # Câu hỏi 2: Có bước bị cấm hoặc bước thừa không?
    forbidden_violations: list[str] = []
    redundant_steps: list[str] = []

    forbidden_set = set(spec.forbidden_tools or ())
    allowed_set = set(spec.allowed_tools) if spec.allowed_tools is not None else None
    counts: dict[str, int] = {}
    seen_signatures: set[tuple[str, str]] = set()

    for c in calls:
        if c.tool in forbidden_set:
            forbidden_violations.append(f"seq={c.seq}: gọi tool bị cấm '{c.tool}'")
        elif allowed_set is not None and c.tool not in allowed_set:
            forbidden_violations.append(f"seq={c.seq}: gọi tool ngoài danh sách cho phép '{c.tool}'")

        counts[c.tool] = counts.get(c.tool, 0) + 1
        max_allowed = (spec.max_calls_per_tool or {}).get(c.tool)
        if max_allowed is not None and counts[c.tool] > max_allowed:
            redundant_steps.append(
                f"seq={c.seq}: gọi thừa '{c.tool}' lần thứ {counts[c.tool]} (tối đa {max_allowed})"
            )

        sig = (c.tool, _canonical_args(c.args))
        if sig in seen_signatures:
            redundant_steps.append(
                f"seq={c.seq}: gọi lặp y hệt '{c.tool}' với cùng tham số"
            )
        else:
            seen_signatures.add(sig)

    no_forbidden_or_redundant = (len(forbidden_violations) == 0) and (len(redundant_steps) == 0)
    overall = gradable and sufficient and no_forbidden_or_redundant

    return TrajectoryGrade(
        passed=overall,
        gradable=True,
        gradability_errors=(),
        sufficient_required_steps=sufficient,
        missing_required_steps=tuple(missing_steps),
        missing_arg_details=tuple(missing_arg_details),
        no_forbidden_or_redundant_steps=no_forbidden_or_redundant,
        forbidden_violations=tuple(forbidden_violations),
        redundant_steps=tuple(redundant_steps),
        observed_sequence=tuple(c.to_dict() for c in calls),
    )
