from __future__ import annotations

import logging
from typing import Any, Optional

from domain.schemas import format_vnd_million
from graph.deps import Deps
from graph.tracing import resolve_trace_target, traced_call, tool_event
from intelligence.nlu import sanitize_user_text
from prompts.advisory_prompt import build_advisory_prompt
from tools.housing_tools import fetch_full_price_stats, lookup_market_price_stats
from utils.text import extract_message_text

logger = logging.getLogger(__name__)

MARKET_PRICE_SKILL_SLUG = "market-price-advisor"
SORRY = "Xin lỗi bạn, Homigo chưa tra cứu được cẩm nang tư vấn này lúc này. Bạn thử hỏi lại sau ít phút, hoặc cho Homigo biết nhu cầu tìm phòng của bạn nhé!"
MAX_GUIDE_CHARS = 6000
MAX_REF_CHARS = 3000


def _resolve_price_stats_fn(deps: Deps):
    if deps.full_price_stats is not None:
        return deps.full_price_stats
    if deps.market_fetcher is not None:
        def _wrapped(city_id: int, district_id: Optional[int] = None, room_type_id: Optional[int] = None):
            general = deps.market_fetcher(city_id, district_id, room_type_id)
            return {"price_stats_general": general, "price_stats_by_area": []} if isinstance(general, dict) else None
        return _wrapped
    return fetch_full_price_stats


def _fmt_price(vnd: Any) -> Optional[str]:
    try:
        v = float(vnd)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return f"{format_vnd_million(v)}/tháng ({int(round(v)):,}đ)".replace(",", ".")


def _format_market_stats_context(stats: dict[str, Any]) -> tuple[str, str]:
    """Tạo khối dữ liệu <market_stats> cho prompt và câu trả lời fallback xác định khi LLM lỗi."""
    loc = str(stats.get("location") or "khu vực yêu cầu")
    rt = stats.get("room_type")
    scope_label = f"{rt} tại {loc}" if rt else f"phòng trọ tại {loc}"

    if stats.get("source") == "nearby_areas":
        areas = list(stats.get("nearby_areas") or [])
        lines = [f"Khu vực lân cận '{loc}' có dữ liệu giá thực tế:"]
        for a in areas:
            name = a.get("name") or a.get("area") or "Khu vực lân cận"
            avg_s = _fmt_price(a.get("average_price_vnd")) or "chưa rõ"
            cnt = a.get("total_listings")
            cnt_s = f" ({cnt} tin)" if cnt is not None else ""
            lines.append(f"- {name}: trung bình {avg_s}{cnt_s}")
        ctx = "<market_stats>\n" + "\n".join(lines) + "\n</market_stats>\n\n"
        fallback = f"📊 **Mặt bằng giá quanh khu vực {loc}:**\n" + "\n".join(lines[1:])
        return ctx, fallback

    total = int(stats.get("total_listings") or 0)
    avg_s = _fmt_price(stats.get("average_price_vnd"))
    min_s = _fmt_price(stats.get("minimum_price_vnd"))
    max_s = _fmt_price(stats.get("maximum_price_vnd"))
    fluct = stats.get("price_fluctuation_month")
    hotspot = stats.get("area_hotspot")

    lines = [
        f"Khu vực: {loc}" + (f" | Loại phòng: {rt}" if rt else ""),
        f"Số tin đăng đang hoạt động: {total} tin",
    ]
    if avg_s:
        lines.append(f"Giá trung bình: {avg_s}")
    if min_s:
        lines.append(f"Giá thấp nhất: {min_s}")
    if max_s:
        lines.append(f"Giá cao nhất: {max_s}")
    if fluct is not None:
        lines.append(f"Biến động tháng gần nhất: {fluct:+.2f}%")
    if hotspot:
        lines.append(f"Khu vực nhiều tin đăng: {hotspot}")

    matched_ward = stats.get("matched_ward_stats")
    if isinstance(matched_ward, dict):
        w_avg = _fmt_price(matched_ward.get("average_price_vnd"))
        if w_avg:
            lines.append(f"Riêng {matched_ward.get('area')}: trung bình {w_avg} ({matched_ward.get('total_listings', 0)} tin)")

    by_area = [a for a in (stats.get("by_area") or []) if isinstance(a, dict)]
    if by_area:
        sub_parts = []
        for a in by_area[:3]:
            s_avg = _fmt_price(a.get("average_price_vnd"))
            if s_avg and a.get("area"):
                sub_parts.append(f"{a['area']} (~{format_vnd_million(float(a['average_price_vnd']))}, {a.get('total_listings', 0)} tin)")
        if sub_parts:
            lines.append("Một số khu vực con tiêu biểu: " + "; ".join(sub_parts))

    ctx = "<market_stats>\n" + "\n".join(lines) + "\n</market_stats>\n\n"

    summary_parts = [f"📊 **Thống kê giá {scope_label}** (dựa trên {total} tin đăng thực tế):"]
    if avg_s:
        summary_parts.append(f"- **Giá trung bình:** {avg_s}")
    if min_s and max_s:
        summary_parts.append(f"- **Khoảng giá phổ biến:** từ {min_s} đến {max_s}")
    if total < 20:
        summary_parts.append("- *Lưu ý: cỡ mẫu hiện còn nhỏ (< 20 tin) nên số liệu chỉ mang tính tham khảo.*")
    summary_parts.append("Bạn có muốn mình tìm giúp phòng phù hợp tại khu vực này không?")
    return ctx, "\n".join(summary_parts)


def _finish_advisory_step(
    state: dict[str, Any],
    text: str,
    *,
    needs_clarify: Optional[bool] = None,
) -> dict[str, Any]:
    """Đóng gói kết quả bước advisory và chuyển tiếp sang pending_tasks tiếp theo (nếu có)."""
    rooms = list(state.get("retrieved_rooms") or [])
    pending = list(state.get("pending_tasks") or [])
    if not pending:
        return {
            "retrieved_rooms": rooms,
            "needs_clarification": bool(needs_clarify) if needs_clarify is not None else False,
            "current_task": None,
            "pending_tasks": [],
            "is_followup": False,
            "final_text": text,
        }

    partials = list(state.get("partial_replies") or [])
    clean_text = str(text or "").strip()
    if clean_text:
        partials.append(clean_text)

    next_task = pending[0]
    rest_tasks = pending[1:]
    if next_task == "followup" and not rooms:
        next_task = rest_tasks[0] if rest_tasks else None
        rest_tasks = rest_tasks[1:] if rest_tasks else []

    if next_task is None:
        return {
            "retrieved_rooms": rooms,
            "partial_replies": partials,
            "needs_clarification": bool(needs_clarify) if needs_clarify is not None else False,
            "current_task": None,
            "pending_tasks": [],
            "is_followup": False,
            "final_text": "",
        }

    step_out: dict[str, Any] = {
        "retrieved_rooms": rooms,
        "partial_replies": partials,
        "current_task": next_task,
        "pending_tasks": rest_tasks,
        "is_followup": (next_task == "followup"),
        "answer_retry_count": 0,
        "answer_issues": [],
        "answer_grounded": True,
        "final_text": "",
        "tool_evidence": [],
    }
    if next_task == "search":
        step_out.update({
            "retrieved_rooms": [],
            "insights": None,
            "needs_clarification": bool(state.get("needs_clarification")),
        })
    elif next_task == "followup":
        step_out["needs_clarification"] = False
    return step_out


def make_advisory_node(deps: Deps):
    def advisory_node(state: dict[str, Any]) -> dict[str, Any]:
        slug = state.get("matched_skill") or ""
        query = sanitize_user_text(state.get("user_message", ""))
        trace = resolve_trace_target(deps).sink()

        try:
            res = tool_event(
                trace,
                "consult_housing_skill",
                {"skill_name": slug, "query": query},
                lambda: deps.consult_skill(slug, query),
                lambda r: {"ok": bool(r.get("ok"))},
                node="advisory_node",
            )
        except Exception:
            res = {}
        guide = str(res.get("instructions") or "") if res.get("ok") else ""
        refs = "\n\n".join(str(v) for v in (res.get("references") or {}).values())[:MAX_REF_CHARS]

        market_ctx_block = ""
        market_fallback = ""
        if slug == MARKET_PRICE_SKILL_SLUG:
            skill_ctx = state.get("skill_context") or {}
            loc_text = str(skill_ctx.get("location_text") or "").strip()
            if not loc_text:
                return _finish_advisory_step(
                    state,
                    (
                        "Bạn muốn tra cứu mặt bằng giá phòng trọ ở quận/huyện hay tỉnh/thành phố nào "
                        "(ví dụ: Gò Vấp, Quận 7, Thủ Đức, Hà Nội)? Mình sẽ tra số liệu thực tế giúp bạn ngay!"
                    ),
                    needs_clarify=True,
                )
            room_type = skill_ctx.get("room_type")
            stats_res = tool_event(
                trace,
                "get_market_price_stats",
                {"location_text": loc_text, "room_type": room_type},
                lambda: lookup_market_price_stats(
                    loc_text,
                    room_type=room_type,
                    region_hint=skill_ctx.get("location_region"),
                    location_kind=skill_ctx.get("location_kind"),
                    admin_lookup_fn=deps.admin_lookup,
                    geocode_fn=deps.geocode,
                    price_stats_fn=_resolve_price_stats_fn(deps),
                ),
                lambda r: {"ok": bool(r.get("ok")), "error": r.get("error"), "total_listings": r.get("total_listings")},
                node="advisory_node",
            )
            if not stats_res.get("ok"):
                if stats_res.get("error") == "AMBIGUOUS_LOCATION":
                    cands = list(stats_res.get("candidates") or [])
                    names = [str(c.get("name")) for c in cands[:4] if c.get("name")]
                    step_res = _finish_advisory_step(
                        state,
                        (
                            f"Khu vực '{loc_text}' có nhiều địa danh trùng tên ({', '.join(names)}). "
                            "Bạn muốn xem thống kê giá ở khu vực cụ thể nào?"
                        ),
                        needs_clarify=True,
                    )
                    if step_res.get("current_task") is None:
                        step_res["follow_up_questions"] = names
                    return step_res
                return _finish_advisory_step(
                    state,
                    (
                        f"Hiện Homigo chưa lấy được dữ liệu thống kê giá thực tế cho khu vực '{loc_text}'. "
                        "Bạn thử nêu rõ tên Quận/Huyện kèm Tỉnh/Thành phố (ví dụ: 'Quận Gò Vấp, TP.HCM') hoặc hỏi khu vực khác nhé!"
                    ),
                )

            if stats_res.get("source") == "price_stats" and (
                int(stats_res.get("total_listings") or 0) <= 0
                or stats_res.get("average_price_vnd") is None
            ):
                resolved_loc = stats_res.get("location") or loc_text
                return _finish_advisory_step(
                    state,
                    (
                        f"Hiện tại hệ thống chưa có tin đăng phòng trọ đang hoạt động có dữ liệu giá tại khu vực {resolved_loc} "
                        "để tính mức giá trung bình."
                    ),
                )

            market_ctx_block, market_fallback = _format_market_stats_context(stats_res)

        model = deps.get_llm()
        if not guide or model is None:
            return _finish_advisory_step(state, market_fallback or SORRY)
        skill = deps.skills().get(slug)
        label = getattr(skill, "name", slug) or slug
        system = build_advisory_prompt(slug, guide[:MAX_GUIDE_CHARS], references=refs, base_prompt=deps.base_prompt)
        session = deps.sessions.get_or_create_session(state["session_id"]) if state.get("session_id") else None
        hist = (
            session.compact_history_as_messages(window=4)
            if session is not None and hasattr(session, "compact_history_as_messages")
            else (session.history_as_messages(window=4) if session is not None and hasattr(session, "history_as_messages") else [])
        )
        msgs: list[tuple[str, str]] = [("system", system)]
        for m in hist:
            role = "human" if getattr(m, "type", "") == "human" else "ai"
            msgs.append((role, extract_message_text(m)))
        msgs.append(("human", f"{market_ctx_block}<user_message>\n{query}\n</user_message>"))
        try:
            reply = traced_call(
                trace,
                lambda: model.invoke(msgs),
                message_count=len(msgs),
                node="advisory_node",
                input_data=msgs,
            )
            text = extract_message_text(reply).strip()
        except Exception:
            logger.warning("advisory_node: LLM lỗi", exc_info=True)
            text = ""
        if len(text) < 30:
            text = market_fallback or SORRY
        elif slug not in text and label not in text:
            text = f"💡 **Homigo AI - Tư vấn chuyên sâu ({label}):**\n\n{text}"
        return _finish_advisory_step(state, text)

    return advisory_node
