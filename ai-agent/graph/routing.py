"""Các hàm điều hướng có điều kiện (Conditional Routing Edges) cho LangGraph State Machine."""

from __future__ import annotations

from typing import Any


def route_after_guardrail(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau guardrail: vi phạm -> formatter_node; hợp lệ -> understand_node."""
    g = state.get("guardrail_result")
    return "formatter_node" if g is not None and not g.allowed else "understand_node"


def _route_pending_task(state: dict[str, Any]) -> str:
    """Ánh xạ current_task kế tiếp trong hàng đợi đa mệnh lệnh sang node tương ứng."""
    cur_task = state.get("current_task")
    if cur_task == "search":
        return "clarification_node" if state.get("needs_clarification") else "retrieval_node"
    if cur_task == "followup":
        return "decision_node"
    if cur_task == "advisory":
        return "advisory_node"
    return "formatter_node"


def route_after_understand(state: dict[str, Any]) -> str:
    """Ngã 5 đường sau understand_node:
    - Vi phạm guardrail hoặc direct_reply (lỗi biên trang / ngoài phạm vi / rỗng trang) -> formatter_node
    - Chuyển trang (page_switched / page_navigation) hoặc Hỏi tiếp về phòng (is_followup) -> decision_node
    - Nhiệm vụ hiện tại là tìm kiếm ('search') -> clarification_node (nếu mơ hồ) hoặc retrieval_node
    - Nhiệm vụ hiện tại hoặc đơn lẻ khớp kỹ năng -> advisory_node
    - Thiếu thông tin / mơ hồ (needs_clarification) -> clarification_node
    - Đủ thông tin tìm phòng -> retrieval_node
    """
    g = state.get("guardrail_result")
    if g is not None and not g.allowed:
        return "formatter_node"
    if state.get("direct_reply"):
        return "formatter_node"
    if state.get("page_switched") or state.get("intent") == "page_navigation":
        return "decision_node"
    if state.get("is_followup"):
        return "decision_node"
    if state.get("current_task") == "search":
        return "clarification_node" if state.get("needs_clarification") else "retrieval_node"
    if state.get("current_task") == "advisory":
        return "advisory_node"
    if state.get("matched_skill"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"


def route_after_retrieval(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau retrieval_node: nếu lỗi định vị (ambiguous/not_found) hoặc lỗi tìm kiếm -> đi thẳng verify_node (bỏ qua decision_node)."""
    if (
        state.get("ambiguous_candidates")
        or state.get("admin_not_found")
        or state.get("location_not_found")
        or state.get("search_error")
    ):
        return "verify_node"
    return "decision_node"


def route_after_verify(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau verify:
    - Còn lượt sửa sai -> node sinh câu trả lời tương ứng (advisory_node hoặc decision_node)
    - Đã đạt và còn nhiệm vụ trong pending_tasks (Plan & Execute đa mệnh lệnh) -> node tiếp theo
    - Đã xong tất cả -> formatter_node
    """
    if not state.get("answer_grounded", True):      # verify_node chỉ đặt False khi CÒN lượt retry
        cur_task = state.get("current_task")
        is_advisory = (cur_task == "advisory") or (
            not cur_task
            and state.get("intent") == "skill_advice"
            and bool(state.get("matched_skill") or state.get("matched_skills"))
        )
        return "advisory_node" if is_advisory else "decision_node"
    return _route_pending_task(state)


def route_after_advisory(state: dict[str, Any]) -> str:
    """Rẽ nhánh sau advisory_node: tiếp tục pending_tasks (search/followup) nếu còn, ngược lại về formatter_node."""
    return _route_pending_task(state)


__all__ = [
    "route_after_advisory",
    "route_after_guardrail",
    "route_after_retrieval",
    "route_after_understand",
    "route_after_verify",
]
