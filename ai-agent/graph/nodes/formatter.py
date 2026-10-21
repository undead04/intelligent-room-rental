from __future__ import annotations

from typing import Any

from graph.deps import Deps
from graph.replies import MAX_HITL_STREAK
from domain.schemas import AgentResponse, UserPreferenceState


def make_formatter_node(deps: Deps):
    def formatter_node(state: dict[str, Any]) -> dict[str, Any]:
        final_text = state.get("final_text", "")
        rooms = state.get("retrieved_rooms") or []
        insights = state.get("insights")
        pref = state.get("preferences") or UserPreferenceState()
        need_clarify = state.get("needs_clarification", False)
        sid = state["session_id"]
        report = state.get("grounding_report")
        session = deps.sessions.get_or_create_session(sid)
        streak = session.hitl_streak

        guard = state.get("guardrail_result")
        blocked = guard is not None and not guard.allowed
        advisory = bool(state.get("matched_skill")) and not state.get("is_followup")
        cands = state.get("ambiguous_candidates") or []

        if blocked:
            follow_up, hitl = [], None
        elif advisory:
            slug = state.get("matched_skill")
            skill = deps.skills().get(slug) if slug else None
            follow_up, hitl = list(getattr(skill, "follow_ups", [])) if skill else [], None
        elif state.get("search_error"):
            follow_up, hitl = ["🔄 Thử tìm lại", "✏️ Tùy chỉnh tiêu chí"], None
            report = {"is_grounded": True, "context_grounded": False, "needs_user_consent": False, "hitl_streak": streak}
        elif state.get("admin_not_found") or state.get("is_keep_criteria"):
            follow_up, hitl, rooms, insights = ["🔍 Thử tìm khu vực khác", "✏️ Tùy chỉnh tiêu chí"], None, [], None
            report = {"is_grounded": True, "groundedness_score": 1.0, "context_grounded": False, "needs_user_consent": False, "hitl_streak": 0}
        elif cands:
            follow_up, hitl, rooms, insights = [str(c.get("name")) for c in cands[:4] if c.get("name")], None, [], None
            need_clarify = True
            report = {"is_grounded": True, "groundedness_score": 1.0, "context_grounded": False, "needs_user_consent": False, "hitl_streak": 0}
        elif need_clarify:
            follow_up = list(state.get("follow_up_questions") or [])
            hitl = None
        elif rooms:
            follow_up = [f"Bạn có muốn xem chi tiết phòng Top 1 ({rooms[0].title[:30]}...) không?"] if rooms else []
            hitl = None
        elif streak > MAX_HITL_STREAK:
            follow_up, hitl = [], None
            report = {"is_grounded": True, "context_grounded": False, "needs_user_consent": False, "hitl_streak": streak, "hitl_limit_reached": True}
        else:
            follow_up, hitl = [], None
            report = dict(report or {})
            report.update({"needs_user_consent": False, "hitl_streak": streak, "hitl_max_streak": MAX_HITL_STREAK})

        response = AgentResponse(
            session_id=sid, text_reply=final_text, rooms=rooms, insights=insights, current_preferences=pref, need_clarification=need_clarify,
            follow_up_questions=follow_up, grounding_report=report, hitl_proposal=None,
            trace_events=list(state.get("trace_events") or []),
        )
        if not blocked:     # tin nhắn bị chặn (injection...) KHÔNG được vào lịch sử, tránh đầu độc các lượt sau
            deps.sessions.commit_turn(session, state.get("user_message", ""), final_text, rooms, searched=bool(state.get("searched")))
        return {"final_response": response}

    return formatter_node
