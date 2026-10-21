"""Thu thập sự kiện model/tool cho frontend (SSE). `traced_call` thay cho đoạn append sự kiện lặp ở clarification/advisory."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler


class TraceCollector(BaseCallbackHandler):
    def __init__(self, events: list[dict[str, Any]]):
        self.events = events
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
        self.events.append({"type": "model_request", "model_call_index": idx, "message_count": len(messages[0]) if messages else 0, "tool_count": len(tools)})

    def on_llm_end(self, response, *, run_id, **kwargs):
        names: list[str] = []
        try:
            names = [tc.get("name") for tc in (getattr(response.generations[0][0].message, "tool_calls", None) or [])]
        except Exception:
            pass
        self.events.append({"type": "model_response", "requested_tools": names, "elapsed_ms": round((time.time() - self._start.pop(run_id, time.time())) * 1000)})

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._start[run_id], self._tool_name[run_id] = time.time(), name
        self.events.append({"type": "tool_started", "tool_name": name, "tool_call_id": str(run_id), "arguments": self._safe(kwargs.get("inputs") or {"input": input_str})})

    def on_tool_end(self, output, *, run_id, **kwargs):
        raw = getattr(output, "content", output)
        raw_str = raw if isinstance(raw, str) else json.dumps(raw, default=str, ensure_ascii=False)
        ok = True
        try:
            parsed = json.loads(raw_str)
            ok = not (isinstance(parsed, dict) and parsed.get("ok") is False)
        except Exception:
            pass
        self.events.append({"type": "tool_finished", "tool_name": self._tool_name.pop(run_id, "tool"), "tool_call_id": str(run_id),
                            "status": "ok" if ok else "error", "elapsed_ms": round((time.time() - self._start.pop(run_id, time.time())) * 1000),
                            "result": {"preview": raw_str[:300]}})

    def on_tool_error(self, error, *, run_id, **kwargs):
        self.events.append({"type": "tool_finished", "tool_name": self._tool_name.pop(run_id, "tool"), "tool_call_id": str(run_id), "status": "error",
                            "elapsed_ms": round((time.time() - self._start.pop(run_id, time.time())) * 1000), "result": {"error": str(error)[:300]}})


def traced_call(events: list[dict[str, Any]], call: Callable[[], Any], *, message_count: int = 2, tool_count: int = 0) -> Any:
    """Gọi một lần LLM thủ công và ghi model_request/model_response (kể cả khi lỗi)."""
    t0 = time.time()
    events.append({"type": "model_request", "model_call_index": sum(1 for e in events if e.get("type") == "model_request") + 1, "message_count": message_count, "tool_count": tool_count})
    try:
        return call()
    finally:
        events.append({"type": "model_response", "requested_tools": [], "elapsed_ms": round((time.time() - t0) * 1000)})


def tool_event(events: list[dict[str, Any]], name: str, args: dict[str, Any], call: Callable[[], Any], summarize: Optional[Callable[[Any], dict]] = None) -> Any:
    """Ghi tool_started/tool_finished quanh một lời gọi hàm."""
    cid = f"call_{name}_{int(time.time() * 1000) % 10**8}"
    t0 = time.time()
    events.append({"type": "tool_started", "tool_name": name, "tool_call_id": cid, "arguments": args})
    try:
        out = call()
    except Exception as e:
        events.append({"type": "tool_finished", "tool_name": name, "tool_call_id": cid, "status": "error", "elapsed_ms": round((time.time() - t0) * 1000), "result": {"error": str(e)[:300]}})
        raise
    events.append({"type": "tool_finished", "tool_name": name, "tool_call_id": cid, "status": "ok", "elapsed_ms": round((time.time() - t0) * 1000), "result": summarize(out) if summarize else {}})
    return out
