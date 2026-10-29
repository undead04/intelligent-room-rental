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
from intelligence.payload_builder import (
    build_decision_context_message,
    build_decision_query_message,
    build_decision_user_message,
)

logger = logging.getLogger(__name__)
MIN_AGENT_REPLY = 30


def _text(m: Any) -> str:
    c = getattr(m, "content", m)
    return c if isinstance(c, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in (c or []))


def followup_fallback_reply(room: Optional[Any], details: Optional[dict[str, Any]] = None) -> str:
    """Fallback an toàn khi việc giải đáp chi tiết phòng gặp lỗi, trích xuất thông tin thực tế từ dữ liệu phòng thay vì dump danh sách phòng."""
    if not room:
        return "Rất tiếc, Homigo chưa thể tải thông tin chi tiết của phòng này. Bạn vui lòng thử lại hoặc liên hệ trực tiếp chủ trọ nhé."
    title = (details and details.get("title")) or getattr(room, "title", "phòng trọ")
    addr = (details and details.get("address")) or getattr(room, "address", "")
    price_val = (details and details.get("price_million")) or (getattr(room, "priceNum", 0) / 1e6 if getattr(room, "priceNum", 0) else "Thoả thuận")
    desc = (details and details.get("description")) or ""
    pet = "Có cho nuôi thú cưng" if (details and details.get("pet_allowed")) else "Chưa có thông tin cho phép nuôi thú cưng"

    msg = [
        f"Về câu hỏi của bạn đối với phòng **{title}** (tại {addr}, giá {price_val} triệu/tháng):",
        f"- Quy định thú cưng: {pet}.",
    ]
    if desc:
        desc_snippet = desc[:250].strip() + "..."
        msg.append(f"- Ghi chú từ chủ phòng: \"{desc_snippet}\"")
    msg.append("Để biết chính xác các chi phí phát sinh (như phụ thu khi ở ghép 2 người, phí gửi xe) hoặc thoả thuận riêng, bạn nên liên hệ trực tiếp chủ nhà khi xem phòng nhé!")
    return "\n\n".join(msg)


def _followup_via_agent(deps: Deps, session: Any, state: dict[str, Any], rooms: list, pref: UserPreferenceState, trace: list) -> tuple[str, list[str]]:
    """Hỏi tiếp về phòng đã đề xuất: agent có công cụ get_listing_detail; trả (văn bản, bằng chứng từ công cụ)."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from tools.housing_tools import compact_listing_detail, dump, fetch_listing_detail

    agent = deps.decision_agent() if deps.decision_agent else None
    if agent is None:
        return "", []

    focus_rank = state.get("focus_rank") or 1
    target_room = rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else (rooms[0] if rooms else None)
    compact_detail: dict[str, Any] = {}
    room_detail_str = ""

    if target_room:
        raw_detail = fetch_listing_detail(target_room.id)
        if raw_detail:
            compact_detail = compact_listing_detail(raw_detail)
            room_detail_str = dump({"ok": True, "data": compact_detail})

    context_msg = build_decision_context_message(
        pref,
        rooms,
        target_room_detail=room_detail_str or None,
    )
    query_msg = build_decision_query_message(
        state.get("user_message", ""),
        focus_rank=focus_rank,
        retry_issues=state.get("answer_issues"),
    )
    hist = session.compact_history_as_messages(window=4) if hasattr(session, "compact_history_as_messages") else session.history_as_messages()

    evidence: list[str] = []
    if room_detail_str:
        evidence.append(room_detail_str)

    try:
        messages = [
            HumanMessage(content=context_msg),
            AIMessage(content="Đã ghi nhận dữ liệu các phòng và tiêu chí tìm kiếm của bạn."),
            *hist,
            HumanMessage(content=query_msg),
        ]
        result = agent.invoke({"messages": messages}, config={"callbacks": [TraceCollector(trace)]})
        msgs = result.get("messages", [])
        evidence.extend(_text(m) for m in msgs if isinstance(m, ToolMessage))
        for m in reversed(msgs):
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                t = _text(m).strip()
                if len(t) > MIN_AGENT_REPLY:
                    return t, evidence
    except Exception:
        logger.warning("_followup_via_agent: agent invoke gặp lỗi", exc_info=True)

    # Nếu agent không trả lời được nhưng có model, thực hiện single-pass QA trực tiếp
    model = deps.get_llm("main")
    if model is not None and target_room and compact_detail:
        try:
            qa_prompt = (
                f"Người dùng đang hỏi về phòng Top {focus_rank}: {compact_detail.get('title', '')}\n"
                f"- Địa chỉ: {compact_detail.get('address', '')}\n"
                f"- Giá phòng: {compact_detail.get('price_million', target_room.price)} triệu/tháng | Tiền cọc: {compact_detail.get('deposit_million', 'Thoả thuận')} triệu\n"
                f"- Diện tích: {compact_detail.get('area_m2', target_room.area_m2)} m²\n"
                f"- Tiện ích: {compact_detail.get('amenities', [])}\n"
                f"- Cho phép nuôi thú cưng: {'Có' if compact_detail.get('pet_allowed') else 'Không / Chưa nêu'}\n"
                f"- Số người ở tối đa: {compact_detail.get('stay_max_people', 'Chưa nêu')}\n"
                f"- Chi phí khác: Điện {compact_detail.get('electricity_cost', 'Chưa rõ')}, Nước {compact_detail.get('water_cost', 'Chưa rõ')}, Dịch vụ {compact_detail.get('service_cost', 'Chưa rõ')}\n"
                f"- Mô tả từ chủ nhà: {compact_detail.get('description', '')}\n\n"
                f"Câu hỏi của người dùng: \"{state.get('user_message', '')}\"\n\n"
                "Yêu cầu: Trả lời trực tiếp, rõ ràng, trung thực và thân thiện. Nếu thông tin không có trong bài đăng, nêu rõ và khuyên liên hệ chủ trọ để xác nhận. Không dump lại danh sách các phòng khác."
            )
            ans = model.invoke([HumanMessage(content=qa_prompt)])
            ans_text = _text(ans).strip()
            if len(ans_text) > MIN_AGENT_REPLY:
                return ans_text, evidence
        except Exception:
            logger.warning("_followup_via_agent: single-pass fallback gặp lỗi", exc_info=True)

    fallback_ans = followup_fallback_reply(target_room, compact_detail)
    return fallback_ans, evidence


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

        focus_rank = state.get("focus_rank") or 1
        target_room = rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else (rooms[0] if rooms else None)
        if not text:
            if state.get("is_followup") and deps.decision_agent is not None:
                text = followup_fallback_reply(target_room)
            else:
                text = template_reply(rooms, insights)
        return {"insights": insights, "final_text": text, "tool_evidence": evidence, "trace_events": trace}

    return decision_node
