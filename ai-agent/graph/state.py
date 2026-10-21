"""Trạng thái luân chuyển qua các node (bước 1-4)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from safety.guardrails import GuardrailResult
from domain.schemas import AgentResponse, DecisionInsight, HitlProposal, RoomItem, UserPreferenceState


class HousingAgentState(TypedDict, total=False):
    # đầu vào
    session_id: str
    user_message: str
    ui_action: Optional[str]                 # HitlAction.value khi người dùng bấm nút (không dò emoji nữa)

    # hiểu lượt chat
    intent: str
    guardrail_result: Optional[GuardrailResult]
    preferences: UserPreferenceState
    multipliers: dict[str, float]
    computed_weights: dict[str, float]
    weight_explanations: list[str]
    semantic_query: Optional[str]
    needs_clarification: bool
    direct_reply: bool
    matched_skill: Optional[str]
    is_contract_query: bool                  # giữ tương thích; dùng matched_skill
    is_followup: bool
    is_keep_criteria: bool
    focus_rank: Optional[int]
    vague_location_info: Optional[dict[str, Any]]
    follow_up_questions: Optional[list[str]]

    # truy xuất
    retrieved_rooms: list[RoomItem]
    searched: bool                           # lượt này có chạy tìm kiếm không (quyết định ghi đè last_rooms)
    search_error: Optional[str]
    admin_not_found: bool
    ambiguous_candidates: list[dict[str, Any]]
    retry_count: int
    context_grounded: bool
    needs_user_consent: bool
    proposed_budget: Optional[float]
    proposed_budget_str: Optional[str]
    hitl_proposal: Optional[HitlProposal]
    last_search_args: Optional[dict[str, Any]]

    # tư vấn + kiểm chứng
    insights: Optional[DecisionInsight]
    final_text: str
    tool_evidence: list[str]
    answer_issues: list[str]
    answer_retry_count: int
    answer_grounded: bool
    retry_notes: list[str]
    grounding_report: Optional[dict[str, Any]]

    # đầu ra
    trace_events: list[dict[str, Any]]
    final_response: Optional[AgentResponse]
