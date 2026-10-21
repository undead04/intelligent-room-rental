from __future__ import annotations

from typing import Any

from graph.deps import Deps
from safety.guardrails import GuardrailResult
from intelligence.understand import interpret_turn


def make_understand_node(deps: Deps):
    def understand_node(state: dict[str, Any]) -> dict[str, Any]:
        session = deps.sessions.get_or_create_session(state["session_id"])
        plan = interpret_turn(state.get("user_message", ""), session, deps.get_llm("fast") if deps.nlu_enabled else None,
                              ui_action=state.get("ui_action"), skills=deps.skills())
        if plan.reset_hitl:
            if hasattr(session, "hitl_streak"):
                session.hitl_streak = 0
            if hasattr(session, "proposed_budget"):
                session.proposed_budget = None
        if plan.commit:                       # NƠI DUY NHẤT ghi tiêu chí/ưu tiên từ lượt chat vào session
            session.preferences = plan.preferences
            session.multipliers = dict(plan.multipliers)
            if hasattr(session, "record_preference_snapshot"):
                session.record_preference_snapshot(plan.preferences)
        out: dict[str, Any] = {
            "intent": plan.intent, "preferences": plan.preferences, "multipliers": plan.multipliers,
            "computed_weights": plan.computed_weights, "weight_explanations": plan.weight_explanations,
            "semantic_query": plan.semantic_query,
            "needs_clarification": plan.needs_clarification, "matched_skill": plan.matched_skill,
            "is_contract_query": bool(plan.matched_skill), "is_keep_criteria": plan.is_keep, "is_followup": plan.is_followup,
            "direct_reply": plan.direct_reply, "focus_rank": plan.focus_rank, "vague_location_info": plan.vague_location_info,
            "retrieved_rooms": list(session.last_rooms) if plan.is_followup else [],
            "searched": False,
        }
        if plan.final_text:
            out["final_text"] = plan.final_text
        if plan.blocked_reason:
            out["guardrail_result"] = GuardrailResult(allowed=False, reason=plan.blocked_reason, safe_response=plan.final_text)
        if plan.used_fallback:
            out["trace_events"] = list(state.get("trace_events") or []) + [{"type": "nlu_fallback"}]
        return out

    return understand_node
