from __future__ import annotations

import logging
from typing import Any, Optional

from domain.enums import amenity_label
from domain.schemas import UserPreferenceState
from graph.deps import Deps
from graph.replies import _format_nearby_bullets, _get_neighboring_areas, reply_when_no_rooms
from graph.tracing import TraceCollector, traced_call
from intelligence.advice import (
    Advice,
    ZeroResultAdvice,
    generate_advice,
    render_advice,
    render_zero_result_advice,
)
from intelligence.insights import build_decision_insights, template_reply
from intelligence.payload_builder import build_decision_user_message

logger = logging.getLogger(__name__)
MIN_AGENT_REPLY = 30


def _text(m: Any) -> str:
    c = getattr(m, "content", m)
    return c if isinstance(c, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in (c or []))


def _followup_via_agent(deps: Deps, session: Any, state: dict[str, Any], rooms: list, pref: UserPreferenceState, trace: list) -> tuple[str, list[str]]:
    """Hỏi tiếp về phòng đã đề xuất: agent có công cụ get_listing_detail; trả (văn bản, bằng chứng từ công cụ)."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    agent = deps.decision_agent() if deps.decision_agent else None
    if agent is None:
        return "", []
    msg = build_decision_user_message(state.get("user_message", ""), pref, rooms, retry_issues=state.get("answer_issues"), focus_rank=state.get("focus_rank"))
    result = agent.invoke({"messages": session.history_as_messages() + [HumanMessage(content=msg)]}, config={"callbacks": [TraceCollector(trace)]})
    msgs = result.get("messages", [])
    evidence = [_text(m) for m in msgs if isinstance(m, ToolMessage)]
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            t = _text(m).strip()
            return (t if len(t) > MIN_AGENT_REPLY else ""), evidence
    return "", evidence


def make_decision_node(deps: Deps):
    def decision_node(state: dict[str, Any]) -> dict[str, Any]:
        rooms = state.get("retrieved_rooms") or []
        trace = list(state.get("trace_events") or [])
        session = deps.sessions.get_or_create_session(state["session_id"])
        if not rooms:
            text = ""
            model = deps.get_llm("main")
            if model is not None and not state.get("search_error") and not state.get("admin_not_found") and not state.get("ambiguous_candidates"):
                try:
                    hitl = state.get("hitl_proposal")
                    pref = state.get("preferences") or UserPreferenceState()
                    loc = (hitl.area_name if hitl and hitl.area_name else None) or pref.location_text or "khu vực này"
                    search_args = state.get("last_search_args") or {}
                    neighbor_bullets = _format_nearby_bullets(loc, pref, search_args)

                    market_ctx = []
                    if hitl and hitl.market_min_price_str:
                        market_ctx.append(f"Giá sàn thấp nhất: {hitl.market_min_price_str}")
                    if hitl and hitl.market_avg_price_str:
                        market_ctx.append(f"Giá trung bình: {hitl.market_avg_price_str}")
                    if hitl and hitl.user_budget_str:
                        market_ctx.append(f"Ngân sách người dùng: {hitl.user_budget_str}")
                    market_str = ", ".join(market_ctx) if market_ctx else "Chưa có số liệu giá chi tiết"

                    amenities_desc = ", ".join(amenity_label(a) for a in pref.amenities) if pref.amenities else "Không yêu cầu tiện ích bắt buộc"

                    prompt = (
                        "Chưa tìm thấy phòng trọ nào khớp 100% điều kiện.\n"
                        f"- Yêu cầu người dùng: '{state.get('user_message', '')}'\n"
                        f"- Khu vực: {loc} | Ngân sách: {pref.max_price / 1e6 if pref.max_price else 'Chưa nêu'} triệu/tháng\n"
                        f"- Tiện ích bắt buộc: {amenities_desc}\n"
                        f"- Số liệu thị trường thực tế: {market_str}\n"
                        f"- Khu vực lân cận thực tế gợi ý:\n{neighbor_bullets}\n\n"
                        "Lưu ý: Đóng vai trò Cố vấn Homigo AI khách quan, chân thành; tuyệt đối không nhắc người dùng bấm nút hay chọn phương án bên dưới."
                    )
                    z_advice = traced_call(trace, lambda: model.with_structured_output(ZeroResultAdvice).invoke([
                        ("system", deps.base_prompt),
                        ("human", prompt),
                    ]))
                    z_advice = z_advice if isinstance(z_advice, ZeroResultAdvice) else ZeroResultAdvice.model_validate(z_advice)
                    text = render_zero_result_advice(z_advice, loc)
                except Exception:
                    logger.warning("decision_node: LLM sinh lời khuyên 0 phòng gặp lỗi, dùng fallback code", exc_info=True)
            if not text:
                text = reply_when_no_rooms(state, session)
            return {"insights": None, "final_text": text, "tool_evidence": [], "trace_events": trace}

        pref = state.get("preferences") or UserPreferenceState()
        insights = build_decision_insights(rooms, state.get("computed_weights"), state.get("weight_explanations"))
        text, evidence = "", []
        try:
            if state.get("is_followup") or (not deps.constrained_generation and deps.decision_agent):
                text, evidence = _followup_via_agent(deps, session, state, rooms, pref, trace)
            else:
                model = deps.get_llm("main")
                advice_sys_prompt = getattr(deps, "advice_system_prompt", None) or deps.decision_system_prompt
                advice = traced_call(trace, lambda: generate_advice(model, advice_sys_prompt, state.get("user_message", ""), pref, rooms,
                                                                    retry_issues=state.get("answer_issues"), focus_rank=state.get("focus_rank"))) if model else None
                text = render_advice(advice, rooms) if advice else ""
        except Exception:
            logger.warning("decision_node: lỗi khi tạo câu tư vấn", exc_info=True)
        return {"insights": insights, "final_text": text or template_reply(rooms, insights), "tool_evidence": evidence, "trace_events": trace}

    return decision_node
