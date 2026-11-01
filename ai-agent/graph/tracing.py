"""Thu thập sự kiện model/tool cho frontend (SSE). `traced_call` thay cho đoạn append sự kiện lặp ở clarification/advisory."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler


def emit_trace(
    events: list[dict[str, Any]],
    event_type: str,
    *,
    node: Optional[str] = None,
    tool: Optional[str] = None,
    **payload: Any,
) -> dict[str, Any]:
    """Ghi một sự kiện chuẩn hoá vào danh sách trace_events (đảm bảo id duy nhất, có node/tool, timestamp không lùi)."""
    now = time.time()
    if events:
        prev_ts = events[-1].get("timestamp")
        if isinstance(prev_ts, (int, float)) and now < prev_ts:
            now = float(prev_ts)
    ev: dict[str, Any] = {
        "id": f"ev_{len(events) + 1}_{uuid.uuid4().hex[:8]}",
        "type": event_type,
        "timestamp": now,
    }
    if tool:
        ev["tool"] = tool
        ev.setdefault("tool_name", tool)
    if node:
        ev["node"] = node
    elif not tool:
        ev["node"] = "agent"
    ev.update(payload)
    events.append(ev)
    return ev


class TraceCollector(BaseCallbackHandler):
    def __init__(self, events: list[dict[str, Any]], node_name: str = "agent"):
        self.events = events
        self.node_name = node_name
        self._start: dict[Any, float] = {}
        self._tool_name: dict[Any, str] = {}

    @staticmethod
    def _safe(obj: Any) -> Any:
        try:
            return json.loads(json.dumps(obj, default=str, ensure_ascii=False))
        except Exception:
            return str(obj)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        idx = sum(1 for e in self.events if e.get("type") == "model_request") + 1
        tools = (kwargs.get("invocation_params") or {}).get("tools") or []
        self._start[run_id] = time.time()
        emit_trace(
            self.events,
            "model_request",
            node=self.node_name,
            model_call_index=idx,
            message_count=len(messages[0]) if messages else 0,
            tool_count=len(tools),
        )

    def on_llm_end(self, response, *, run_id, **kwargs):
        names: list[str] = []
        try:
            names = [tc.get("name") for tc in (getattr(response.generations[0][0].message, "tool_calls", None) or [])]
        except Exception:
            pass
        prompt_tokens: int = 0
        cached_tokens: int = 0
        try:
            gen = response.generations[0][0]
            meta = getattr(gen.message, "response_metadata", {}) or {}
            usage = meta.get("token_usage", {}) or getattr(response, "llm_output", {}).get("token_usage", {}) or {}
            prompt_tokens = usage.get("prompt_tokens") or 0
            details = usage.get("prompt_tokens_details") or {}
            cached_tokens = details.get("cached_tokens") or 0
        except Exception:
            pass
        extra: dict[str, Any] = {
            "requested_tools": names,
            "elapsed_ms": round((time.time() - self._start.pop(run_id, time.time())) * 1000),
        }
        if prompt_tokens > 0:
            extra["prompt_tokens"] = prompt_tokens
        if cached_tokens > 0:
            extra["cached_tokens"] = cached_tokens
        emit_trace(self.events, "model_response", node=self.node_name, **extra)

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._start[run_id], self._tool_name[run_id] = time.time(), name
        emit_trace(
            self.events,
            "tool_started",
            node=self.node_name,
            tool=name,
            tool_name=name,
            tool_call_id=str(run_id),
            arguments=self._safe(kwargs.get("inputs") or {"input": input_str}),
        )

    def on_tool_end(self, output, *, run_id, **kwargs):
        raw = getattr(output, "content", output)
        raw_str = raw if isinstance(raw, str) else json.dumps(raw, default=str, ensure_ascii=False)
        ok = True
        try:
            parsed = json.loads(raw_str)
            ok = not (isinstance(parsed, dict) and parsed.get("ok") is False)
        except Exception:
            pass
        tname = self._tool_name.pop(run_id, "tool")
        emit_trace(
            self.events,
            "tool_finished",
            node=self.node_name,
            tool=tname,
            tool_name=tname,
            tool_call_id=str(run_id),
            status="ok" if ok else "error",
            elapsed_ms=round((time.time() - self._start.pop(run_id, time.time())) * 1000),
            result={"preview": raw_str[:300]},
        )

    def on_tool_error(self, error, *, run_id, **kwargs):
        tname = self._tool_name.pop(run_id, "tool")
        emit_trace(
            self.events,
            "tool_finished",
            node=self.node_name,
            tool=tname,
            tool_name=tname,
            tool_call_id=str(run_id),
            status="error",
            elapsed_ms=round((time.time() - self._start.pop(run_id, time.time())) * 1000),
            result={"error": str(error)[:300]},
        )


def traced_call(
    events: list[dict[str, Any]],
    call: Callable[[], Any],
    *,
    message_count: int = 2,
    tool_count: int = 0,
    node: str = "llm",
) -> Any:
    """Gọi một lần LLM thủ công và ghi model_request/model_response (kể cả khi lỗi)."""
    t0 = time.time()
    idx = sum(1 for e in events if e.get("type") == "model_request") + 1
    emit_trace(events, "model_request", node=node, model_call_index=idx, message_count=message_count, tool_count=tool_count)
    try:
        return call()
    finally:
        emit_trace(events, "model_response", node=node, requested_tools=[], elapsed_ms=round((time.time() - t0) * 1000))


def tool_event(
    events: list[dict[str, Any]],
    name: str,
    args: dict[str, Any],
    call: Callable[[], Any],
    summarize: Optional[Callable[[Any], dict]] = None,
    *,
    node: str = "retrieval_node",
) -> Any:
    """Ghi tool_started/tool_finished quanh một lời gọi hàm."""
    cid = f"call_{name}_{int(time.time() * 1000) % 10**8}"
    t0 = time.time()
    emit_trace(events, "tool_started", node=node, tool=name, tool_name=name, tool_call_id=cid, arguments=args)
    try:
        out = call()
    except Exception as e:
        emit_trace(
            events,
            "tool_finished",
            node=node,
            tool=name,
            tool_name=name,
            tool_call_id=cid,
            status="error",
            elapsed_ms=round((time.time() - t0) * 1000),
            result={"error": str(e)[:300]},
        )
        raise
    emit_trace(
        events,
        "tool_finished",
        node=node,
        tool=name,
        tool_name=name,
        tool_call_id=cid,
        status="ok",
        elapsed_ms=round((time.time() - t0) * 1000),
        result=summarize(out) if summarize else {},
    )
    return out
