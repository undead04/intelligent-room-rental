from __future__ import annotations

import math
from typing import Any

from core.session_store import DEFAULT_PAGE_SIZE, MAX_PAGED_ROOMS, MAX_PAGINATION_PAGES
from domain.schemas import AgentResponse, UserPreferenceState
from graph.deps import Deps
from graph.tracing import resolve_trace_target


def make_formatter_node(deps: Deps):
    def formatter_node(state: dict[str, Any]) -> dict[str, Any]:
        final_text = state.get("final_text", "")
        partials = [p.strip() for p in (state.get("partial_replies") or []) if isinstance(p, str) and p.strip()]
        cur_text = str(final_text or "").strip()
        if partials:
            if cur_text and cur_text not in partials:
                partials.append(cur_text)
            final_text = "\n\n".join(partials)
        rooms = state.get("retrieved_rooms") or []
        insights = state.get("insights")
        pref = state.get("preferences") or UserPreferenceState()
        need_clarify = state.get("needs_clarification", False)
        sid = state["session_id"]
        report = state.get("grounding_report")
        session = deps.sessions.get_or_create_session(sid)

        guard = state.get("guardrail_result")
        blocked = guard is not None and not guard.allowed
        advisory_slugs = [str(s).strip() for s in (state.get("matched_skills") or []) if str(s or "").strip()]
        if not advisory_slugs and state.get("matched_skill"):
            advisory_slugs = [str(state["matched_skill"]).strip()]
        advisory = bool(advisory_slugs) and not state.get("is_followup")
        cands = state.get("ambiguous_candidates") or []

        if blocked:
            follow_up = []
        elif advisory and not state.get("searched") and not rooms and not need_clarify:
            skills_map = deps.skills()
            collected_followups: list[str] = []
            for slug in advisory_slugs:
                skill = skills_map.get(slug)
                for q in (getattr(skill, "follow_ups", []) if skill else []):
                    if q not in collected_followups:
                        collected_followups.append(q)
            follow_up = collected_followups
        elif state.get("search_error"):
            follow_up = ["🔄 Thử tìm lại", "✏️ Tùy chỉnh tiêu chí"]
            report = {"is_grounded": True, "context_grounded": False}
        elif state.get("admin_not_found"):
            follow_up, rooms, insights = ["🔍 Thử tìm khu vực khác", "✏️ Tùy chỉnh tiêu chí"], [], None
            report = {**dict(report or {}), "is_grounded": True, "groundedness_score": 1.0, "context_grounded": False}
        elif state.get("location_not_found"):
            follow_up, rooms, insights = ["📍 Nhập kèm Quận/Thành phố", "🔍 Thử tìm khu vực khác"], [], None
            need_clarify = True
            report = {**dict(report or {}), "is_grounded": True, "groundedness_score": 1.0, "context_grounded": False}
        elif cands:
            follow_up, rooms, insights = [str(c.get("name")) for c in cands[:4] if c.get("name")], [], None
            need_clarify = True
            report = {**dict(report or {}), "is_grounded": True, "groundedness_score": 1.0, "context_grounded": False}
        elif need_clarify:
            follow_up = list(state.get("follow_up_questions") or [])
        elif rooms:
            follow_up = [f"Bạn có muốn xem chi tiết phòng Top 1 ({rooms[0].title[:30]}...) không?"] if rooms else []
        else:
            follow_up = []
            report = dict(report or {})

        searched = bool(state.get("searched"))
        page_switched = bool(state.get("page_switched"))
        if blocked or state.get("admin_not_found") or state.get("location_not_found") or cands:
            paged_pool = []
            cur_page = 1
        elif searched:
            paged_pool = list(state.get("paged_rooms") if state.get("paged_rooms") is not None else rooms)[:MAX_PAGED_ROOMS]
            cur_page = 1
        elif page_switched:
            paged_pool = list(getattr(session, "paged_rooms", None) or rooms)[:MAX_PAGED_ROOMS]
            cur_page = int(state.get("current_page") or 1)
        else:
            paged_pool = list(getattr(session, "paged_rooms", None) or getattr(session, "last_rooms", None) or [])[:MAX_PAGED_ROOMS]
            cur_page = int(getattr(session, "current_page", 1) or 1)

        total_rooms = len(paged_pool)
        total_pages = min(MAX_PAGINATION_PAGES, max(1, math.ceil(total_rooms / DEFAULT_PAGE_SIZE))) if total_rooms > 0 else 0
        eff_page = max(1, min(cur_page, total_pages)) if total_pages > 0 else 1

        response = AgentResponse(
            session_id=sid,
            text_reply=final_text,
            rooms=rooms,
            insights=insights,
            current_preferences=pref,
            need_clarification=need_clarify,
            follow_up_questions=follow_up,
            grounding_report=report,
            trace_events=resolve_trace_target(deps).snapshot(),
            searched=searched,
            page=eff_page,
            page_size=DEFAULT_PAGE_SIZE,
            total_rooms=total_rooms,
            total_pages=total_pages,
        )
        if not blocked:     # tin nhắn bị chặn (injection...) KHÔNG được vào lịch sử, tránh đầu độc các lượt sau
            deps.sessions.commit_turn(
                session,
                state.get("user_message", ""),
                final_text,
                rooms,
                searched=searched,
                paged_rooms=paged_pool if searched else None,
                current_page=eff_page,
                page_switched=page_switched,
            )
        return {"final_response": response}

    return formatter_node
