"""Trạng thái luân chuyển qua các node."""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from domain.schemas import AgentResponse, DecisionInsight, RoomItem, UserPreferenceState
from safety.guardrails import GuardrailResult


class HousingAgentState(TypedDict, total=False):
    # đầu vào
    session_id: str
    user_message: str

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
    proposed_budget: Optional[float]
    proposed_budget_str: Optional[str]
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
    dod_report: Optional[dict[str, Any]]
    verifier_result: Optional[dict[str, Any]]
    verifier_decision: Optional[str]

    # đầu ra (trace được cô lập trong TraceStore, KHÔNG nằm trong state)
    final_response: Optional[AgentResponse]
