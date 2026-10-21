from __future__ import annotations

from typing import Any

from intelligence.understand import route_after_understand  # noqa: F401  (re-export)


def route_after_guardrail(state: dict[str, Any]) -> str:
    g = state.get("guardrail_result")
    return "formatter_node" if g is not None and not g.allowed else "understand_node"


def route_after_verify(state: dict[str, Any]) -> str:
    if not state.get("answer_grounded", True):      # verify_node chỉ đặt False khi CÒN lượt retry
        return "decision_node"
    return "formatter_node"
