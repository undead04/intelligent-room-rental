from __future__ import annotations

from typing import Any

from graph.deps import Deps
from graph.tracing import resolve_trace_target, traced_call
from intelligence.understand import interpret_turn
from safety.guardrails import GuardrailResult


def make_understand_node(deps: Deps):
    def understand_node(state: dict[str, Any]) -> dict[str, Any]:
        session = deps.sessions.get_or_create_session(state["session_id"])
        fast_llm = deps.get_llm("fast")
        trace = resolve_trace_target(deps).sink()
        user_msg = state.get("user_message", "")

        def _run_interpret():
            return interpret_turn(
                user_msg,
                session,
                fast_llm,
                skills=deps.skills(),
            )

        if fast_llm is not None:
            plan = traced_call(
                trace,
                _run_interpret,
                message_count=2,
                tool_count=0,
                node="understand_node",
                input_data={
                    "user_message": user_msg,
                    "preferences": session.preferences.to_context_string(),
                },
                output_extractor=lambda p: {
                    "intent": p.intent,
                    "needs_clarification": p.needs_clarification,
                    "matched_skill": p.matched_skill,
                    "is_followup": p.is_followup,
                    "patch": p.analysis.patch,
                },
            )
        else:
            plan = _run_interpret()
        if plan.commit:                       # NƠI DUY NHẤT ghi tiêu chí/ưu tiên từ lượt chat vào session
            session.preferences = plan.preferences
            session.multipliers = dict(plan.multipliers)
            if hasattr(session, "pending_ambiguous_location"):
                session.pending_ambiguous_location = None
            if hasattr(session, "pending_ambiguous_candidates"):
                session.pending_ambiguous_candidates = []
            if hasattr(session, "record_preference_snapshot"):
                session.record_preference_snapshot(plan.preferences)
        if plan.focus_rank is not None:
            session.focused_room_rank = plan.focus_rank
        all_tasks = ([plan.current_task] if plan.current_task else []) + list(plan.pending_tasks)
        need_prior_rooms = plan.is_followup or (
            "followup" in all_tasks
            and ("search" not in all_tasks or all_tasks.index("followup") < all_tasks.index("search"))
        )
        out: dict[str, Any] = {
            "intent": plan.intent,
            "preferences": plan.preferences,
            "multipliers": plan.multipliers,
            "computed_weights": plan.computed_weights,
            "weight_explanations": plan.weight_explanations,
            "semantic_query": plan.semantic_query,
            "needs_clarification": plan.needs_clarification,
            "matched_skill": plan.matched_skill,
            "skill_context": plan.skill_context,
            "current_task": plan.current_task,
            "pending_tasks": list(plan.pending_tasks),
            "partial_replies": [],
            "is_followup": plan.is_followup,
            "direct_reply": plan.direct_reply,
            "focus_rank": plan.focus_rank,
            "vague_location_info": plan.vague_location_info,
            "retrieved_rooms": list(session.last_rooms) if need_prior_rooms else [],
            "searched": False,
        }
        if plan.final_text:
            out["final_text"] = plan.final_text
        if plan.blocked_reason:
            out["guardrail_result"] = GuardrailResult(allowed=False, reason=plan.blocked_reason, safe_response=plan.final_text)
        return out

    return understand_node
