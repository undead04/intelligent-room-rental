from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.llm import invoke_with_retry
from domain.enums import amenity_label
from domain.schemas import _CONCEPT_TAGS, UserPreferenceState
from graph.deps import Deps
from graph.replies import _format_nearby_bullets, reply_when_no_rooms
from graph.tracing import TraceCollector, resolve_trace_target, tool_event, traced_call
from intelligence.advice import (
    ZeroResultAdvice,
    generate_advice,
    render_advice,
    render_zero_result_advice,
)
from intelligence.insights import (
    build_decision_insights,
    template_reply,
)
from intelligence.payload_builder import (
    build_decision_context_message,
    build_decision_query_message,
)
from prompts.decision_prompt import (
    build_zero_result_system_prompt,
    build_zero_result_user_prompt,
)
from tools.housing_tools import compact_listing_detail, dump, fetch_listing_detail
from utils.text import extract_message_text, strip_accents

logger = logging.getLogger(__name__)
MIN_AGENT_REPLY = 30

_DEEP_DETAIL_KEYWORDS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:coc|dat\s+coc|tien\s+coc|deposit)\b"),
    re.compile(r"\bdien\b(?!\s+tich\b)"),
    re.compile(
        r"\b(?:nuoc|gui\s+xe|giu\s+xe|bai\s+xe|nha\s+xe|phu\s+thu|phi|dich\s+vu|chi\s+phi|"
        r"rac|wifi|internet|tien\s+mang|lap\s+mang|cap\s+quang)\b"
    ),
    re.compile(r"\b(?:chu\s+tro|chu\s+nha|lien\s+he|sdt|so\s+dien\s+thoai|nguoi\s+dang)\b"),
    re.compile(
        r"\b(?:mo\s+ta|chi\s+tiet|noi\s+quy|gio\s+giac|tu\s+do|ve\s+muon|hop\s+dong|"
        r"thu\s+cung|nuoi|pet|meo|nuoi\s+cho|con\s+cho|cho\s+meo)\b"
    ),
    re.compile(
        r"\b(?:bao\s+ve|thang\s+may|may\s+lanh|dieu\s+hoa|gac|wc|ve\s+sinh|"
        r"may\s+giat|tu\s+lanh|ban\s+cong|cua\s+so|bep|noi\s+that|chung\s+chu|"
        r"van\s+tay|camera|an\s+ninh|pccc)\b"
    ),
)

_SURFACE_FIELD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:gia|gia\s+thue|bao\s+nhieu\s+tien|dien\s+tich|m2|met\s+vuong|"
        r"rong\s+bao\s+nhieu|khoang\s+cach|cach\s+bao\s+xa|bao\s+xa|"
        r"bao\s+nhieu\s+km|may\s+km|dia\s+chi|duong\s+nao|phuong\s+nao|quan\s+nao|"
        r"o\s+dau|diem\s+phu\s+hop|match|phan\s+tram|loai\s+phong|"
        r"phong\s+ngu|phong\s+tam|phong\s+ve\s+sinh|may\s+phong)\b"
    ),
)

_MULTI_ROOM_COMPARE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:so\s+sanh|phong\s+nao|cai\s+nao|can\s+nao|trong\s+cac\s+phong|"
        r"top\s+\d+\s+(?:va|voi)\s+top\s+\d+|re\s+nhat|re\s+hon|rong\s+nhat|rong\s+hon|"
        r"gan\s+nhat|gan\s+hon|tot\s+nhat|tot\s+hon|phu\s+hop\s+nhat|cao\s+nhat|thap\s+nhat)\b"
    ),
)


def _has_deep_detail_keyword(norm_msg: str) -> bool:
    return any(p.search(norm_msg) for p in _DEEP_DETAIL_KEYWORDS)


def _is_multi_room_comparison(norm_msg: str) -> bool:
    return any(p.search(norm_msg) for p in _MULTI_ROOM_COMPARE_PATTERNS) and not _has_deep_detail_keyword(norm_msg)


def _needs_deep_listing_detail(
    user_message: str,
    explicit_focus: Optional[int],
    followup_current_page_first: bool = False,
) -> bool:
    """Xác định câu hỏi follow-up có cần gọi `get_listing_detail` hay đã có đủ thông tin trong `rooms`."""
    norm = " ".join(strip_accents(user_message or "").split())
    if not norm:
        return explicit_focus is not None or followup_current_page_first
    if _has_deep_detail_keyword(norm):
        return True
    if _is_multi_room_comparison(norm) and not followup_current_page_first:
        return False
    if any(p.search(norm) for p in _SURFACE_FIELD_PATTERNS):
        return False
    return True


def _detail_from_room_item(room: Any) -> dict[str, Any]:
    """Trích xuất thông tin chi tiết chuẩn từ `RoomItem` đã lưu sẵn trong state lúc search (0 gọi API)."""
    raw_desc = getattr(room, "description", None)
    raw_dep = getattr(room, "deposit", None)
    raw_contact = getattr(room, "contact_name", None)
    if not (raw_desc or raw_dep or raw_contact):
        return {}

    compact: dict[str, Any] = {}
    if getattr(room, "id", None):
        compact["id"] = room.id
    if getattr(room, "title", None):
        compact["title"] = room.title
    if getattr(room, "price", None):
        compact["price"] = room.price
    price_num = getattr(room, "priceNum", 0) or 0
    if isinstance(price_num, (int, float)) and price_num > 0:
        compact["price_million"] = round(float(price_num) / 1_000_000, 2)
    if isinstance(raw_dep, (int, float)) and raw_dep > 0:
        compact["deposit"] = float(raw_dep)
        compact["deposit_million"] = round(float(raw_dep) / 1_000_000, 2)
    if getattr(room, "area_m2", None):
        compact["area_m2"] = room.area_m2
    if getattr(room, "bedrooms", None) is not None:
        compact["bedrooms"] = room.bedrooms
    if getattr(room, "bathrooms", None) is not None:
        compact["bathrooms"] = room.bathrooms
    rt = getattr(room, "room_type", None)
    if rt is not None and getattr(rt, "label_vi", None):
        compact["room_type_name"] = rt.label_vi
    if getattr(room, "address", None):
        compact["address"] = room.address

    concept_scores = getattr(room, "concept_scores", None) or {}
    amenities: list[str] = []
    if isinstance(concept_scores, dict):
        for k, label in _CONCEPT_TAGS.items():
            sc = concept_scores.get(k)
            if isinstance(sc, (int, float)) and sc >= 0.5 and label not in amenities:
                amenities.append(label)
        if "pet_allowed" in concept_scores:
            compact["pet_allowed"] = bool(concept_scores["pet_allowed"] >= 0.5)
    for tag in getattr(room, "inferred_tags", None) or ():
        if tag not in amenities:
            amenities.append(tag)
    if amenities:
        compact["amenities"] = amenities
    if raw_contact:
        compact["contact_name"] = raw_contact
    if raw_desc:
        compact["description"] = raw_desc
    return compact


def followup_fallback_reply(room: Optional[Any], details: Optional[dict[str, Any]] = None) -> str:
    """Fallback an toàn khi việc giải đáp chi tiết phòng gặp lỗi, trích xuất thông tin thực tế từ dữ liệu phòng."""
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


def _followup_via_agent(deps: Deps, session: Any, state: dict[str, Any], rooms: list, pref: UserPreferenceState, trace: Any) -> tuple[str, list[str]]:
    """Tư vấn tự do qua ReAct Decision Agent (cho cả hỏi tiếp chi tiết lẫn kết quả tìm mới khi constrained_generation=False)."""
    agent = deps.decision_agent() if deps.decision_agent else None
    if agent is None:
        return "", []

    is_followup = bool(state.get("is_followup"))
    user_message = state.get("user_message", "")
    norm_user_msg = " ".join(strip_accents(user_message).split())
    followup_page_first = bool(state.get("followup_current_page_first"))
    is_multi_compare = is_followup and not followup_page_first and _is_multi_room_comparison(norm_user_msg)
    explicit_focus = None if is_multi_compare else (state.get("focus_rank") if is_followup else None)
    focus_rank: Optional[int] = (
        explicit_focus
        if explicit_focus is not None
        else ((getattr(session, "focused_room_rank", None) or 1) if (is_followup and not is_multi_compare) else None)
    )
    target_room = (
        next(
            (r for r in rooms if getattr(r, "rank", None) == focus_rank),
            rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else (rooms[0] if rooms else None),
        )
        if focus_rank is not None
        else None
    )
    compact_detail: dict[str, Any] = {}
    room_detail_str = ""
    is_retry = int(state.get("answer_retry_count") or 0) > 0
    prior_evidence = list(state.get("tool_evidence") or [])
    details_cache = getattr(session, "room_details_cache", None)

    if target_room:
        cached_detail = details_cache.get(target_room.id) if isinstance(details_cache, dict) else None
        needs_deep = _needs_deep_listing_detail(user_message, explicit_focus, followup_page_first)
        if needs_deep or (isinstance(cached_detail, dict) and cached_detail):
            state_detail = _detail_from_room_item(target_room)
            if state_detail:
                compact_detail = state_detail
                room_detail_str = dump({"ok": True, "data": compact_detail})
                if isinstance(details_cache, dict):
                    details_cache[target_room.id] = dict(compact_detail)
            elif isinstance(cached_detail, dict) and cached_detail:
                compact_detail = dict(cached_detail)
                room_detail_str = dump({"ok": True, "data": compact_detail})
            elif is_retry:
                room_detail_str = next(
                    (str(ev) for ev in prior_evidence if isinstance(ev, str) and ev.strip().startswith("{") and target_room.id in ev),
                    "",
                )
            elif needs_deep:
                res = tool_event(
                    trace,
                    "get_listing_detail",
                    {"listing_id": target_room.id},
                    lambda: fetch_listing_detail(target_room.id),
                    node="decision_node",
                )
                if isinstance(res, dict) and res.get("ok") and isinstance(res.get("data"), dict):
                    compact_detail = compact_listing_detail(res.get("data"))
                    room_detail_str = dump({"ok": True, "data": compact_detail})
                    if isinstance(details_cache, dict) and compact_detail:
                        details_cache[target_room.id] = dict(compact_detail)

    cur_task = state.get("current_task")
    pending_tasks = list(state.get("pending_tasks") or [])
    has_pending_followup = (cur_task == "search" and "followup" in pending_tasks)
    if has_pending_followup:
        scoped_q = (state.get("semantic_query") or state.get("user_message", "")).strip()
        effective_question = (
            f"{scoped_q}\n"
            "(Lưu ý phạm vi bước này: chỉ tóm tắt và so sánh ngắn gọn các phòng vừa tìm được; "
            "KHÔNG gọi `get_listing_detail` vì phần kiểm tra chi tiết phòng sẽ chạy ở bước kế tiếp.)"
        )
    else:
        effective_question = state.get("user_message", "")

    context_msg = build_decision_context_message(pref, rooms)
    query_msg = build_decision_query_message(
        effective_question,
        focus_rank=focus_rank,
        retry_issues=state.get("answer_issues"),
        target_room_detail=room_detail_str or None,
    )
    if is_followup:
        hist = (
            session.compact_history_as_messages(window=4)
            if hasattr(session, "compact_history_as_messages")
            else session.history_as_messages()
        )
    else:
        hist = []

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
        result = invoke_with_retry(
            lambda: agent.invoke({"messages": messages}, config={"callbacks": [TraceCollector(trace, node_name="decision_node")]}),
            context="decision_node",
        )
        msgs = result.get("messages", [])
        for m in msgs:
            if isinstance(m, ToolMessage):
                raw_txt = extract_message_text(m).strip()
                evidence.append(raw_txt)
                if isinstance(details_cache, dict) and raw_txt.startswith("{"):
                    try:
                        parsed = json.loads(raw_txt)
                    except (ValueError, TypeError):
                        parsed = None
                    if isinstance(parsed, dict) and parsed.get("ok") and isinstance(parsed.get("data"), dict):
                        d_item = parsed["data"]
                        lid = d_item.get("id")
                        if isinstance(lid, str) and lid:
                            details_cache[lid] = dict(d_item)
        for m in reversed(msgs):
            if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                t = extract_message_text(m).strip()
                if len(t) > MIN_AGENT_REPLY:
                    return t, evidence
    except Exception:
        logger.warning("_followup_via_agent: agent invoke gặp lỗi", exc_info=True)

    model = deps.get_llm()
    if is_followup and model is not None and target_room and compact_detail:
        try:
            dep_val = compact_detail.get("deposit_million")
            dep_str = f"{dep_val} triệu" if dep_val else "Thoả thuận"
            price_val = compact_detail.get("price_million", target_room.price)
            price_str = f"{price_val} triệu/tháng" if isinstance(price_val, (int, float)) else str(price_val)
            qa_prompt = (
                f"Người dùng đang hỏi về phòng Top {focus_rank}: {compact_detail.get('title', '')}\n"
                f"- Địa chỉ: {compact_detail.get('address', '')}\n"
                f"- Giá phòng: {price_str} | Tiền cọc: {dep_str}\n"
                f"- Diện tích: {compact_detail.get('area_m2', target_room.area_m2)} m²\n"
                f"- Tiện ích đã xác thực: {compact_detail.get('amenities', [])}\n"
                f"- Cho phép nuôi thú cưng: {'Có' if compact_detail.get('pet_allowed') else 'Không / Chưa nêu'}\n"
                f"- Người đăng / Liên hệ: {compact_detail.get('contact_name', 'Chủ trọ')}\n"
                f"- Mô tả chi tiết từ chủ nhà (chứa thông tin điện, nước, phụ phí nếu có): {compact_detail.get('description', '')}\n\n"
                f"Câu hỏi của người dùng: \"{state.get('user_message', '')}\"\n\n"
                "Yêu cầu: Trả lời trực tiếp, rõ ràng, trung thực và thân thiện. Ưu tiên trích xuất chi phí điện, nước, gửi xe và nội quy từ phần mô tả của chủ nhà. Nếu thông tin không có trong bài đăng, nêu rõ và khuyên liên hệ chủ trọ để xác nhận. Không dump lại danh sách các phòng khác."
            )
            ans = traced_call(
                trace,
                lambda: model.invoke([HumanMessage(content=qa_prompt)]),
                message_count=1,
                node="decision_node",
                input_data=qa_prompt,
            )
            ans_text = extract_message_text(ans).strip()
            if len(ans_text) > MIN_AGENT_REPLY:
                return ans_text, evidence
        except Exception:
            logger.warning("_followup_via_agent: single-pass fallback gặp lỗi", exc_info=True)

    if is_followup:
        fallback_ans = followup_fallback_reply(target_room, compact_detail)
        return fallback_ans, evidence
    return "", evidence


def make_decision_node(deps: Deps):
    def decision_node(state: dict[str, Any]) -> dict[str, Any]:
        rooms = state.get("retrieved_rooms") or []
        trace = resolve_trace_target(deps).sink()
        session = deps.sessions.get_or_create_session(state["session_id"])
        if not rooms:
            text = ""
            evidence_blocks: list[str] = []
            model = deps.get_llm()
            if model is not None and not state.get("search_error") and not state.get("admin_not_found") and not state.get("location_not_found") and not state.get("ambiguous_candidates"):
                try:
                    market = state.get("market_context")
                    pref = state.get("preferences") or UserPreferenceState()
                    loc = (market.area_name if market and market.area_name else None) or pref.location_text or "khu vực này"
                    search_args = state.get("last_search_args") or {}
                    neighbor_bullets = _format_nearby_bullets(pref, search_args)
                    dropped_summary = [str(x).strip() for x in (state.get("dropped_summary") or []) if str(x).strip()]

                    market_ctx = []
                    if market and market.market_min_price_str:
                        market_ctx.append(f"Giá sàn thấp nhất: {market.market_min_price_str}")
                    if market and market.market_avg_price_str:
                        market_ctx.append(f"Giá trung bình: {market.market_avg_price_str}")
                    if market and market.user_budget_str:
                        market_ctx.append(f"Ngân sách người dùng: {market.user_budget_str}")
                    market_str = ", ".join(market_ctx) if market_ctx else "Chưa có số liệu giá chi tiết"

                    if market_ctx:
                        evidence_blocks.append(market_str)
                    if neighbor_bullets:
                        evidence_blocks.append(neighbor_bullets)
                    if dropped_summary:
                        evidence_blocks.extend(dropped_summary)

                    amenities_desc = ", ".join(amenity_label(a) for a in pref.amenities) if pref.amenities else "Không yêu cầu tiện ích bắt buộc"
                    radius_km = search_args.get("max_distance_km") if isinstance(search_args, dict) else None
                    if radius_km is not None:
                        evidence_blocks.append(f"Bán kính tìm kiếm tối đa: {float(radius_km):g} km")

                    prompt = build_zero_result_user_prompt(
                        user_message=state.get("user_message", ""),
                        loc=loc,
                        max_price=pref.max_price,
                        amenities_desc=amenities_desc,
                        market_str=market_str,
                        neighbor_bullets=neighbor_bullets,
                        pref_summary=pref.to_context_string(),
                        radius_km=float(radius_km) if radius_km is not None else None,
                        dropped_summary=dropped_summary,
                        retry_issues=state.get("answer_issues") or (),
                    )

                    model_queues = getattr(model, "queues", None)
                    use_legacy_zero_schema = (
                        isinstance(model_queues, dict)
                        and ("ZeroResultAdvice" in model_queues)
                        and ("text" not in model_queues)
                    )
                    if use_legacy_zero_schema:
                        z_advice = traced_call(
                            trace,
                            lambda: model.with_structured_output(ZeroResultAdvice).invoke([
                                ("system", deps.base_prompt),
                                ("human", prompt),
                            ]),
                            node="decision_node",
                            input_data=[("system", deps.base_prompt), ("human", prompt)],
                        )
                        z_advice = z_advice if isinstance(z_advice, ZeroResultAdvice) else ZeroResultAdvice.model_validate(z_advice)
                        text = render_zero_result_advice(z_advice, loc)
                    else:
                        zero_sys = build_zero_result_system_prompt(deps.base_prompt)
                        reply = traced_call(
                            trace,
                            lambda: model.invoke([
                                ("system", zero_sys),
                                ("human", prompt),
                            ]),
                            message_count=2,
                            node="decision_node",
                            input_data=[("system", zero_sys), ("human", prompt)],
                        )
                        cand_text = extract_message_text(reply).strip()
                        if len(cand_text) >= MIN_AGENT_REPLY:
                            text = cand_text
                except Exception:
                    logger.warning("decision_node: LLM sinh lời khuyên 0 phòng gặp lỗi, dùng fallback code", exc_info=True)
            if not text:
                text = reply_when_no_rooms(state, session)
            return {"insights": None, "final_text": text, "tool_evidence": evidence_blocks}

        pref = state.get("preferences") or UserPreferenceState()
        insights = state.get("insights") or build_decision_insights(rooms, state.get("weight_explanations"))
        text, evidence = "", []
        try:
            if state.get("is_followup") or (not deps.constrained_generation and deps.decision_agent):
                text, evidence = _followup_via_agent(deps, session, state, rooms, pref, trace)
            else:
                model = deps.get_llm()
                advice_sys_prompt = getattr(deps, "advice_system_prompt", None) or deps.decision_system_prompt
                advice = traced_call(
                    trace,
                    lambda: generate_advice(
                        model,
                        advice_sys_prompt,
                        state.get("user_message", ""),
                        pref,
                        rooms,
                        retry_issues=state.get("answer_issues"),
                        focus_rank=state.get("focus_rank"),
                    ),
                    node="decision_node",
                    input_data={
                        "user_message": state.get("user_message", ""),
                        "room_count": len(rooms),
                        "retry_issues": state.get("answer_issues"),
                        "focus_rank": state.get("focus_rank"),
                    },
                ) if model else None
                text = render_advice(advice, rooms) if advice else ""
        except Exception:
            logger.warning("decision_node: lỗi khi tạo câu tư vấn", exc_info=True)

        focus_rank = state.get("focus_rank") or getattr(session, "focused_room_rank", None) or 1
        target_room = next(
            (r for r in rooms if getattr(r, "rank", None) == focus_rank),
            rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else (rooms[0] if rooms else None),
        )
        if not text:
            if state.get("is_followup") and deps.decision_agent is not None:
                text = followup_fallback_reply(target_room)
            else:
                text = template_reply(rooms, insights)
        return {"insights": insights, "final_text": text, "tool_evidence": evidence}

    return decision_node
