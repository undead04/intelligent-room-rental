from __future__ import annotations

from typing import Any

from graph.deps import Deps
from core.session_store import new_session_id


def make_guardrail_node(deps: Deps):
    def guardrail_node(state: dict[str, Any]) -> dict[str, Any]:
        sid = state.get("session_id") or new_session_id()          # không còn session "default" dùng chung
        guard = deps.guard(state.get("user_message", ""))
        out: dict[str, Any] = {"session_id": sid, "guardrail_result": guard}
        if not guard.allowed:
            out.update(final_text=guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI.", needs_clarification=False, retrieved_rooms=[])
        return out

    return guardrail_node
