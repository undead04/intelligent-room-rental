"""Thu thập và cô lập Trace dạng JSONL (Append-Only) phục vụ DoD Verifier và Frontend SSE.

Thiết kế:
- `TraceStore`: kho lưu trữ sự kiện độc lập hoàn toàn với `HousingAgentState` (append-only, đóng băng bản chụp khi verifier đọc).
- Mỗi span tương ứng một dòng JSONL chuẩn với `run_id`, `seq`, `ts`, `type`, `versions` (prompt/skill/model), `case_id` (nếu có).
- `tool_event` và `TraceCollector` ghi đầy đủ `args`, `result` (không cắt bớt), `error`, `duration_ms`, cùng `state_before` / `state_after` nếu tool tác động trạng thái.
- `traced_call` và `TraceCollector` ghi đầy đủ `input`, `output`, `tokens_in`, `tokens_out`, `duration_ms`.
- `redact_sensitive_data`: tự động che khóa API, token, SĐT, email, số giấy tờ trước khi lưu vết.
"""

from __future__ import annotations

import copy
import contextvars
import json
import os
import re
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler

from core import paths

PROMPT_VERSION = "homigo-prompt-v2.0"
SKILL_VERSION = "housing-skills-v1.0"

_SENSITIVE_KEY_EXACT = frozenset({
    "api_key",
    "openai_api_key",
    "gemini_api_key",
    "google_api_key",
    "anthropic_api_key",
    "authorization",
    "x-api-key",
    "secret",
    "secret_key",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
})
_SENSITIVE_KEY_SUFFIXES = ("_api_key", "_secret", "_password", "_secret_key")

_API_KEY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(\bBearer\s+)[A-Za-z0-9._\-]{12,}", re.IGNORECASE), r"\1[REDACTED_API_KEY]"),
    (
        re.compile(
            r"((?:openai_api_key|gemini_api_key|google_api_key|api_key|secret_key)\s*[=:]\s*[\"']?)[^\s\"';,]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED_API_KEY]",
    ),
)
_PHONE_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:\+84|0)(?:3|5|7|8|9)(?:[.\-\s]?\d){8}(?![A-Za-z0-9_])")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_ID_CARD_RE = re.compile(
    r"((?:cccd|cmnd|căn cước|can cuoc|số giấy tờ|so giay to)\s*[:#]?\s*)\d{9,12}\b",
    re.IGNORECASE,
)


def deep_freeze(obj: Any) -> Any:
    """Đóng băng đệ quy cấu trúc dict/list/set thành MappingProxyType/tuple bất biến cho Verifier."""
    if isinstance(obj, Mapping):
        return MappingProxyType({k: deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple, set, frozenset)):
        return tuple(deep_freeze(item) for item in obj)
    return obj


def _redact_string(text: str) -> str:
    s = text
    for pat, repl in _API_KEY_PATTERNS:
        s = pat.sub(repl, s)
    s = _EMAIL_RE.sub("[REDACTED_EMAIL]", s)
    s = _PHONE_RE.sub("[REDACTED_PHONE]", s)
    s = _ID_CARD_RE.sub(r"\1[REDACTED_ID]", s)
    return s


def redact_sensitive_data(obj: Any) -> Any:
    """Che dữ liệu nhạy cảm và khóa API một cách đệ quy trước khi ghi span vào TraceStore."""
    if isinstance(obj, str):
        return _redact_string(obj)
    if isinstance(obj, Mapping):
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            kl = str(k).strip().lower()
            if kl in _SENSITIVE_KEY_EXACT or kl.endswith(_SENSITIVE_KEY_SUFFIXES):
                out[k] = "[REDACTED_API_KEY]"
            else:
                out[k] = redact_sensitive_data(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_sensitive_data(x) for x in obj]
    return obj


def _to_plain_json_obj(obj: Any) -> Any:
    """Chuyển đối tượng Python (Pydantic, dataclass, LangChain message, dict...) thành dữ liệu JSON không mất nội dung."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        try:
            return _to_plain_json_obj(obj.model_dump(mode="json"))
        except Exception:
            pass
    if is_dataclass(obj) and not isinstance(obj, type):
        try:
            return _to_plain_json_obj(asdict(obj))
        except Exception:
            pass
    if isinstance(obj, Mapping):
        return {str(k): _to_plain_json_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_plain_json_obj(x) for x in obj]
    if hasattr(obj, "content"):
        role = getattr(obj, "type", obj.__class__.__name__)
        out: dict[str, Any] = {"role": str(role), "content": _to_plain_json_obj(getattr(obj, "content", ""))}
        tc = getattr(obj, "tool_calls", None)
        if tc:
            out["tool_calls"] = _to_plain_json_obj(tc)
        return out
    try:
        return json.loads(json.dumps(obj, default=str, ensure_ascii=False))
    except Exception:
        return str(obj)


def _safe_redacted(obj: Any) -> Any:
    return redact_sensitive_data(_to_plain_json_obj(obj))


def _estimate_tokens(obj: Any) -> int:
    if obj is None or obj == "" or obj == [] or obj == {}:
        return 0
    try:
        raw = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        raw = str(obj)
    raw = raw.strip()
    if not raw:
        return 0
    return max(1, (len(raw) + 3) // 4)


def _extract_model_metrics(res: Any, input_obj: Any = None) -> dict[str, Any]:
    """Trích xuất output và thông số tokens_in / tokens_out từ kết quả gọi model."""
    tokens_in = 0
    tokens_out = 0
    cached_tokens = 0
    requested_tools: list[str] = []
    tokens_estimated = False

    msg = res
    llm_output: dict[str, Any] = {}
    if hasattr(res, "generations") and getattr(res, "generations", None):
        try:
            llm_output = getattr(res, "llm_output", None) or {}
            msg = getattr(res.generations[0][0], "message", res.generations[0][0])
        except Exception:
            pass

    if hasattr(msg, "tool_calls") and getattr(msg, "tool_calls", None):
        for tc in getattr(msg, "tool_calls") or []:
            if isinstance(tc, dict) and tc.get("name"):
                requested_tools.append(str(tc["name"]))

    usage_meta = getattr(msg, "usage_metadata", None)
    if isinstance(usage_meta, Mapping):
        tokens_in = int(usage_meta.get("input_tokens") or usage_meta.get("prompt_tokens") or 0)
        tokens_out = int(usage_meta.get("output_tokens") or usage_meta.get("completion_tokens") or 0)
        details = usage_meta.get("input_token_details") or {}
        if isinstance(details, Mapping):
            cached_tokens = int(details.get("cache_read") or details.get("cached_tokens") or 0)

    if tokens_in == 0 and tokens_out == 0:
        resp_meta = getattr(msg, "response_metadata", None) or {}
        usage = (
            (resp_meta.get("token_usage") if isinstance(resp_meta, Mapping) else None)
            or (resp_meta.get("usage") if isinstance(resp_meta, Mapping) else None)
            or (llm_output.get("token_usage") if isinstance(llm_output, Mapping) else None)
            or {}
        )
        if isinstance(usage, Mapping):
            tokens_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            tokens_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            details = usage.get("prompt_tokens_details") or {}
            if isinstance(details, Mapping):
                cached_tokens = int(details.get("cached_tokens") or 0)

    plain_output = _safe_redacted(getattr(msg, "content", msg) if hasattr(msg, "content") and not requested_tools else msg)
    if tokens_in == 0 and input_obj is not None:
        est_in = _estimate_tokens(input_obj)
        if est_in > 0:
            tokens_in = est_in
            tokens_estimated = True
    if tokens_out == 0 and plain_output is not None:
        est_out = _estimate_tokens(plain_output)
        if est_out > 0:
            tokens_out = est_out
            tokens_estimated = True

    return {
        "output": plain_output,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cached_tokens": cached_tokens,
        "tokens_estimated": tokens_estimated,
        "requested_tools": requested_tools,
    }


def resolve_versions(
    *,
    prompt_version: Optional[str] = None,
    skill_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> dict[str, str]:
    """Chuẩn hóa metadata phiên bản gắn vào từng span."""
    return {
        "prompt": str(prompt_version or os.getenv("PROMPT_VERSION") or PROMPT_VERSION),
        "skill": str(skill_version or os.getenv("SKILL_VERSION") or SKILL_VERSION),
        "model": str(model_version or os.getenv("MODEL_NAME") or "default"),
    }


class TraceSink:
    """Cửa ghi nối tiếp (write-only) cấp cho các Node; không cho phép đọc/sửa/xóa trace cũ."""

    def __init__(self, store: "TraceStore") -> None:
        self._store = store

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        return self._store.append(event)


class TraceStore:
    """Kho lưu trữ span chuẩn JSONL hoàn toàn tách biệt khỏi `HousingAgentState`."""

    def __init__(
        self,
        *,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        case_id: Optional[str] = None,
        versions: Optional[Mapping[str, str]] = None,
        persist: bool = False,
        persist_path: Optional[Path] = None,
    ) -> None:
        self.run_id: str = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self.session_id: Optional[str] = session_id
        self.case_id: Optional[str] = case_id if case_id is not None else get_active_case_id()
        self.versions: dict[str, str] = (
            {str(k): str(v) for k, v in versions.items()}
            if versions
            else resolve_versions()
        )
        self.persist: bool = persist
        self.persist_path: Path = Path(persist_path) if persist_path else (paths.TRACES_DIR / "verifier_traces.jsonl")
        self._events: list[dict[str, Any]] = []
        self._seq: int = 0

    def sink(self) -> TraceSink:
        return TraceSink(self)

    def _next_ts(self) -> float:
        now = time.time()
        if self._events:
            prev_ts = self._events[-1].get("ts")
            if isinstance(prev_ts, (int, float)) and now < prev_ts:
                now = float(prev_ts)
        return now

    def append(self, raw_event: Mapping[str, Any]) -> dict[str, Any]:
        """Ghi nối tiếp 1 span (tự gán run_id, seq, ts, versions, case_id và che dữ liệu nhạy cảm)."""
        self._seq += 1
        now = raw_event.get("ts") or raw_event.get("timestamp")
        if not isinstance(now, (int, float)):
            now = self._next_ts()
        elif self._events:
            prev_ts = self._events[-1].get("ts")
            if isinstance(prev_ts, (int, float)) and now < prev_ts:
                now = float(prev_ts)

        ev: dict[str, Any] = _safe_redacted(dict(raw_event))
        ev["run_id"] = self.run_id
        ev["seq"] = self._seq
        ev["ts"] = float(now)
        ev["timestamp"] = float(now)
        ev.setdefault("id", f"ev_{self._seq}_{uuid.uuid4().hex[:8]}")
        ev["versions"] = dict(self.versions)
        if self.session_id is not None:
            ev.setdefault("session_id", self.session_id)
        eff_case = ev.get("case_id") if ev.get("case_id") is not None else (self.case_id or get_active_case_id())
        if eff_case is not None:
            ev["case_id"] = eff_case

        stored = copy.deepcopy(ev)
        self._events.append(stored)
        if self.persist:
            self._append_jsonl_line(stored)
        return copy.deepcopy(stored)

    def _append_jsonl_line(self, ev: Mapping[str, Any]) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.persist_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")

    def snapshot(self) -> list[dict[str, Any]]:
        """Trả về bản sao sâu danh sách span theo đúng thứ tự `seq`."""
        return copy.deepcopy(sorted(self._events, key=lambda e: int(e.get("seq", 0))))

    def frozen_snapshot(self) -> tuple[Mapping[str, Any], ...]:
        """Trả về bản chụp bất biến tuyệt đối cho DoD Verifier đọc (cấm ghi đè/xóa)."""
        ordered = sorted(self._events, key=lambda e: int(e.get("seq", 0)))
        return deep_freeze(ordered)

    def to_jsonl(self) -> str:
        """Xuất toàn bộ các span của lượt chạy thành các dòng JSONL."""
        ordered = sorted(self._events, key=lambda e: int(e.get("seq", 0)))
        return "\n".join(json.dumps(ev, ensure_ascii=False, default=str) for ev in ordered)

    def count_type(self, event_type: str) -> int:
        return sum(1 for e in self._events if e.get("type") == event_type)


_ACTIVE_TRACE_STORE: contextvars.ContextVar[Optional[TraceStore]] = contextvars.ContextVar(
    "homigo_active_trace_store",
    default=None,
)
_ACTIVE_CASE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "homigo_active_case_id",
    default=None,
)


def get_active_trace_store() -> Optional[TraceStore]:
    return _ACTIVE_TRACE_STORE.get()


def bind_trace_store(store: Optional[TraceStore]) -> contextvars.Token[Optional[TraceStore]]:
    return _ACTIVE_TRACE_STORE.set(store)


def reset_trace_store(token: contextvars.Token[Optional[TraceStore]]) -> None:
    _ACTIVE_TRACE_STORE.reset(token)


def get_active_case_id() -> Optional[str]:
    return _ACTIVE_CASE_ID.get()


def bind_case_id(case_id: Optional[str]) -> contextvars.Token[Optional[str]]:
    return _ACTIVE_CASE_ID.set(case_id)


def reset_case_id(token: contextvars.Token[Optional[str]]) -> None:
    _ACTIVE_CASE_ID.reset(token)


def resolve_trace_target(deps: Any = None) -> TraceStore:
    """Lấy `TraceStore` đang hoạt động từ ContextVar hoặc Deps (bỏ qua mock không phải TraceStore)."""
    active = get_active_trace_store()
    if active is not None:
        return active
    if deps is not None:
        raw_store = getattr(deps, "trace_store", None)
        if isinstance(raw_store, TraceStore):
            return raw_store
        getter = getattr(deps, "get_trace_store", None)
        if callable(getter):
            candidate = getter()
            if isinstance(candidate, TraceStore):
                return candidate
    return TraceStore()


def _legacy_enrich(events: list[dict[str, Any]], raw_event: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    if events:
        prev_ts = events[-1].get("ts", events[-1].get("timestamp"))
        if isinstance(prev_ts, (int, float)) and now < prev_ts:
            now = float(prev_ts)
    seq = len(events) + 1
    run_id = events[0].get("run_id") if events else f"run_{uuid.uuid4().hex[:12]}"
    ev: dict[str, Any] = _safe_redacted(raw_event)
    ev.setdefault("run_id", run_id)
    ev["seq"] = seq
    ev["ts"] = float(now)
    ev["timestamp"] = float(now)
    ev["id"] = f"ev_{seq}_{uuid.uuid4().hex[:8]}"
    ev.setdefault("versions", resolve_versions())
    eff_case = get_active_case_id()
    if eff_case is not None:
        ev.setdefault("case_id", eff_case)
    events.append(ev)
    return ev


TraceTarget = Union[TraceStore, TraceSink, list[dict[str, Any]], None]


def emit_trace(
    events: TraceTarget,
    event_type: str,
    *,
    node: Optional[str] = None,
    tool: Optional[str] = None,
    **payload: Any,
) -> dict[str, Any]:
    """Ghi một span chuẩn JSONL vào TraceStore/TraceSink hoặc danh sách trace cục bộ."""
    base: dict[str, Any] = {"type": event_type}
    if tool:
        base["tool"] = tool
        base.setdefault("tool_name", tool)
    if node:
        base["node"] = node
    elif not tool:
        base["node"] = "agent"
    base.update(payload)

    if isinstance(events, (TraceStore, TraceSink)):
        return events.append(base)
    if isinstance(events, list):
        stored = _legacy_enrich(events, base)
        active = get_active_trace_store()
        if active is not None:
            active.append(base)
        return stored

    active = get_active_trace_store()
    if active is not None:
        return active.append(base)
    return _legacy_enrich([], base)


def emit_verifier_span(
    events: TraceTarget,
    *,
    verifier_output: Mapping[str, Any],
    next_decision: str,
    failed_tier: Optional[str] = None,
    node: str = "verify_node",
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Ghi span riêng cho kết quả DoD Verifier và quyết định tiếp theo của ứng dụng."""
    payload: dict[str, Any] = {
        "verifier_output": dict(verifier_output),
        "passed": bool(verifier_output.get("passed", False)),
        "failures": list(verifier_output.get("failures") or []),
        "next_decision": next_decision,
    }
    if failed_tier is not None:
        payload["failed_tier"] = failed_tier
    if extra:
        payload.update(dict(extra))
    return emit_trace(events, "verifier_decision", node=node, **payload)


def _count_model_requests(target: TraceTarget) -> int:
    if isinstance(target, TraceStore):
        return target.count_type("model_request")
    if isinstance(target, TraceSink):
        return target._store.count_type("model_request")
    if isinstance(target, list):
        return sum(1 for e in target if e.get("type") == "model_request")
    active = get_active_trace_store()
    return active.count_type("model_request") if active is not None else 0


class TraceCollector(BaseCallbackHandler):
    """LangChain CallbackHandler ghi bọc quanh từng model call và tool call."""

    def __init__(self, events: TraceTarget, node_name: str = "agent"):
        self.events = events
        self.node_name = node_name
        self._start: dict[Any, float] = {}
        self._tool_name: dict[Any, str] = {}
        self._tool_args: dict[Any, Any] = {}
        self._model_inputs: dict[Any, Any] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        idx = _count_model_requests(self.events) + 1
        tools = (kwargs.get("invocation_params") or {}).get("tools") or []
        self._start[run_id] = time.time()
        safe_input = _safe_redacted(messages[0] if messages else [])
        self._model_inputs[run_id] = safe_input
        emit_trace(
            self.events,
            "model_request",
            node=self.node_name,
            model_call_index=idx,
            message_count=len(messages[0]) if messages else 0,
            tool_count=len(tools),
            input=safe_input,
        )

    def on_llm_end(self, response, *, run_id, **kwargs):
        start_t = self._start.pop(run_id, time.time())
        duration_ms = round((time.time() - start_t) * 1000)
        safe_input = self._model_inputs.pop(run_id, None)
        metrics = _extract_model_metrics(response, input_obj=safe_input)
        emit_trace(
            self.events,
            "model_response",
            node=self.node_name,
            input=safe_input,
            output=metrics["output"],
            tokens_in=metrics["tokens_in"],
            tokens_out=metrics["tokens_out"],
            prompt_tokens=metrics["tokens_in"],
            cached_tokens=metrics["cached_tokens"],
            tokens_estimated=metrics["tokens_estimated"],
            requested_tools=metrics["requested_tools"],
            duration_ms=duration_ms,
            elapsed_ms=duration_ms,
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        start_t = self._start.pop(run_id, time.time())
        duration_ms = round((time.time() - start_t) * 1000)
        safe_input = self._model_inputs.pop(run_id, None)
        emit_trace(
            self.events,
            "model_error",
            node=self.node_name,
            input=safe_input,
            error=_redact_string(str(error)),
            tokens_in=_estimate_tokens(safe_input),
            tokens_out=0,
            duration_ms=duration_ms,
            elapsed_ms=duration_ms,
        )

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        raw_args = kwargs.get("inputs")
        if raw_args is None:
            try:
                raw_args = json.loads(input_str) if isinstance(input_str, str) else input_str
            except Exception:
                raw_args = {"input": input_str}
        safe_args = _safe_redacted(raw_args)
        self._start[run_id] = time.time()
        self._tool_name[run_id] = name
        self._tool_args[run_id] = safe_args
        emit_trace(
            self.events,
            "tool_started",
            node=self.node_name,
            tool=name,
            tool_name=name,
            tool_call_id=str(run_id),
            args=safe_args,
            arguments=safe_args,
        )

    def on_tool_end(self, output, *, run_id, **kwargs):
        raw = getattr(output, "content", output)
        parsed_result: Any = raw
        if isinstance(raw, str):
            try:
                parsed_result = json.loads(raw)
            except Exception:
                parsed_result = raw
        ok = True
        err_msg: Optional[str] = None
        if isinstance(parsed_result, Mapping) and parsed_result.get("ok") is False:
            ok = False
            if parsed_result.get("error"):
                err_msg = str(parsed_result.get("error"))
        tname = self._tool_name.pop(run_id, "tool")
        safe_args = self._tool_args.pop(run_id, {})
        duration_ms = round((time.time() - self._start.pop(run_id, time.time())) * 1000)
        emit_trace(
            self.events,
            "tool_finished",
            node=self.node_name,
            tool=tname,
            tool_name=tname,
            tool_call_id=str(run_id),
            args=safe_args,
            arguments=safe_args,
            status="ok" if ok else "error",
            duration_ms=duration_ms,
            elapsed_ms=duration_ms,
            result=_safe_redacted(parsed_result),
            error=_redact_string(err_msg) if err_msg else None,
        )

    def on_tool_error(self, error, *, run_id, **kwargs):
        tname = self._tool_name.pop(run_id, "tool")
        safe_args = self._tool_args.pop(run_id, {})
        duration_ms = round((time.time() - self._start.pop(run_id, time.time())) * 1000)
        err_str = _redact_string(str(error))
        emit_trace(
            self.events,
            "tool_finished",
            node=self.node_name,
            tool=tname,
            tool_name=tname,
            tool_call_id=str(run_id),
            args=safe_args,
            arguments=safe_args,
            status="error",
            duration_ms=duration_ms,
            elapsed_ms=duration_ms,
            result=None,
            error=err_str,
        )


def traced_call(
    events: TraceTarget,
    call: Callable[[], Any],
    *,
    message_count: int = 2,
    tool_count: int = 0,
    node: str = "llm",
    input_data: Any = None,
    output_extractor: Optional[Callable[[Any], Any]] = None,
) -> Any:
    """Gọi một lần LLM thủ công và ghi đầy đủ model_request/model_response (kể cả khi lỗi)."""
    t0 = time.time()
    idx = _count_model_requests(events) + 1
    safe_input = _safe_redacted(input_data) if input_data is not None else None
    emit_trace(
        events,
        "model_request",
        node=node,
        model_call_index=idx,
        message_count=message_count,
        tool_count=tool_count,
        input=safe_input,
    )
    err_str: Optional[str] = None
    out: Any = None
    try:
        out = call()
        return out
    except Exception as exc:
        err_str = _redact_string(str(exc))
        raise
    finally:
        duration_ms = round((time.time() - t0) * 1000)
        extracted = output_extractor(out) if (out is not None and output_extractor is not None) else out
        metrics = _extract_model_metrics(extracted, input_obj=safe_input)
        emit_trace(
            events,
            "model_response",
            node=node,
            model_call_index=idx,
            input=safe_input,
            output=metrics["output"] if err_str is None else None,
            tokens_in=metrics["tokens_in"],
            tokens_out=0 if err_str is not None else metrics["tokens_out"],
            cached_tokens=metrics["cached_tokens"],
            tokens_estimated=metrics["tokens_estimated"],
            requested_tools=metrics["requested_tools"],
            error=err_str,
            duration_ms=duration_ms,
            elapsed_ms=duration_ms,
        )


def tool_event(
    events: TraceTarget,
    name: str,
    args: dict[str, Any],
    call: Callable[[], Any],
    summarize: Optional[Callable[[Any], dict]] = None,
    *,
    node: str = "retrieval_node",
    state_before: Any = None,
    state_after: Any = None,
) -> Any:
    """Ghi tool_started/tool_finished quanh một lời gọi hàm; không cắt bớt args/result và hỗ trợ state_before/state_after."""
    cid = f"call_{name}_{int(time.time() * 1000) % 10**8}_{uuid.uuid4().hex[:4]}"
    t0 = time.time()
    before_val = _safe_redacted(state_before() if callable(state_before) else state_before) if state_before is not None else None
    safe_args = _safe_redacted(args)
    started_payload: dict[str, Any] = {
        "tool_call_id": cid,
        "args": safe_args,
        "arguments": safe_args,
    }
    if before_val is not None:
        started_payload["state_before"] = before_val
    emit_trace(events, "tool_started", node=node, tool=name, **started_payload)

    try:
        out = call()
    except Exception as e:
        duration_ms = round((time.time() - t0) * 1000)
        after_err = _safe_redacted(state_after() if callable(state_after) else state_after) if state_after is not None else None
        err_payload: dict[str, Any] = {
            "tool_call_id": cid,
            "args": safe_args,
            "arguments": safe_args,
            "status": "error",
            "duration_ms": duration_ms,
            "elapsed_ms": duration_ms,
            "result": None,
            "error": _redact_string(str(e)),
        }
        if before_val is not None:
            err_payload["state_before"] = before_val
        if after_err is not None:
            err_payload["state_after"] = after_err
        emit_trace(events, "tool_finished", node=node, tool=name, **err_payload)
        raise

    duration_ms = round((time.time() - t0) * 1000)
    after_val = _safe_redacted(state_after() if callable(state_after) else state_after) if state_after is not None else None
    safe_result = _safe_redacted(out)
    ok = not (isinstance(out, Mapping) and out.get("ok") is False)
    err_msg = _redact_string(str(out.get("error"))) if (isinstance(out, Mapping) and out.get("error") and not ok) else None

    fin_payload: dict[str, Any] = {
        "tool_call_id": cid,
        "args": safe_args,
        "arguments": safe_args,
        "status": "ok" if ok else "error",
        "duration_ms": duration_ms,
        "elapsed_ms": duration_ms,
        "result": safe_result,
        "error": err_msg,
    }
    if summarize is not None:
        fin_payload["result_summary"] = _safe_redacted(summarize(out))
    if before_val is not None:
        fin_payload["state_before"] = before_val
    if after_val is not None:
        fin_payload["state_after"] = after_val

    emit_trace(events, "tool_finished", node=node, tool=name, **fin_payload)
    return out
