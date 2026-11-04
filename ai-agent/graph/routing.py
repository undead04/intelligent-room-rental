"""Các hàm điều hướng có điều kiện (Conditional Routing Edges) cho LangGraph State Machine."""

from __future__ import annotations

from typing import Any


def route_after_guardrail(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau guardrail: vi phạm -> formatter_node; hợp lệ -> understand_node."""
    g = state.get("guardrail_result")
    return "formatter_node" if g is not None and not g.allowed else "understand_node"


def route_after_understand(state: dict[str, Any]) -> str:
    """Ngã 5 đường sau understand_node:
    - Vi phạm guardrail hoặc direct_reply -> formatter_node
    - Hỏi tiếp về phòng cũ (is_followup) -> decision_node
    - Khớp kỹ năng cẩm nang (matched_skill) -> advisory_node
    - Thiếu thông tin / mơ hồ (needs_clarification) -> clarification_node
    - Đủ thông tin tìm phòng -> retrieval_node
    """
    g = state.get("guardrail_result")
    if g is not None and not g.allowed:
        return "formatter_node"
    if state.get("direct_reply"):
        return "formatter_node"
    if state.get("is_followup"):
        return "decision_node"
    if state.get("matched_skill"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"


def route_after_verify(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau verify: còn lượt sửa sai -> decision_node; đã chuẩn xác -> formatter_node."""
    if not state.get("answer_grounded", True):      # verify_node chỉ đặt False khi CÒN lượt retry
        return "decision_node"
    return "formatter_node"


__all__ = [
    "route_after_guardrail",
    "route_after_understand",
    "route_after_verify",
]
