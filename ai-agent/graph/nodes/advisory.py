from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool as lc_tool

from domain.schemas import format_vnd_million
from graph.deps import Deps
from graph.tracing import resolve_trace_target, traced_call, tool_event
from intelligence.nlu import sanitize_user_text
from prompts.advisory_prompt import build_advisory_prompt, build_multi_advisory_prompt
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
    evidence: Optional[list[str]] = None,
    follow_up_questions: Optional[list[str]] = None,
    reused_cached_skills: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Đóng gói kết quả bước advisory để chuyển qua `verify_node` kiểm định trước khi đi tiếp."""
    has_pending = bool(state.get("pending_tasks"))
    out: dict[str, Any] = {
        "final_text": text,
        "tool_evidence": list(evidence or []),
        "needs_clarification": (
            bool(needs_clarify)
            if needs_clarify is not None
            else (bool(state.get("needs_clarification")) if has_pending else False)
        ),
        "answer_grounded": True,
        "reused_cached_skills": list(reused_cached_skills or []),
    }
    if follow_up_questions is not None:
        out["follow_up_questions"] = follow_up_questions
    return out


def _resolve_advisory_slugs(state: dict[str, Any]) -> list[str]:
    slugs = [str(s).strip() for s in (state.get("matched_skills") or []) if str(s or "").strip()]
    primary = str(state.get("matched_skill") or "").strip()
    if primary and primary not in slugs:
        slugs.insert(0, primary) if not slugs else slugs.append(primary)
    return list(dict.fromkeys(slugs))


def _query_market_stats_for_location(
    deps: Deps,
    trace: Any,
    loc_text: str,
    *,
    room_type: Optional[str] = None,
    region_hint: Optional[str] = None,
    location_kind: Optional[str] = None,
) -> tuple[str, str, Optional[str], list[str]]:
    """Thực thi tra cứu giá thị trường cho 1 địa danh -> `(ctx_block, fallback_text, clarify_kind, followups)`."""
    stats_res = tool_event(
        trace,
        "get_market_price_stats",
        {"location_text": loc_text, "room_type": room_type},
        lambda: lookup_market_price_stats(
            loc_text,
            room_type=room_type,
            region_hint=region_hint,
            location_kind=location_kind,
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
            bullets = "\n".join(f"{idx}. **{n}**" for idx, n in enumerate(names, 1))
            msg = (
                f"📍 Khu vực **{loc_text}** có nhiều địa danh trùng tên:\n\n"
                f"{bullets}\n\n"
                "👉 Bạn muốn xem thống kê giá ở khu vực cụ thể nào?"
            )
            return f"<market_stats>\n{msg}\n</market_stats>\n\n", msg, "ambiguous", names
        msg = (
            f"Hiện Homigo chưa lấy được dữ liệu thống kê giá thực tế cho khu vực '{loc_text}'. "
            "Bạn thử nêu rõ tên Quận/Huyện kèm Tỉnh/Thành phố (ví dụ: 'Quận Gò Vấp, TP.HCM') hoặc hỏi khu vực khác nhé!"
        )
        return f"<market_stats>\n{msg}\n</market_stats>\n\n", msg, "not_found", []

    if stats_res.get("source") == "price_stats" and (
        int(stats_res.get("total_listings") or 0) <= 0
        or stats_res.get("average_price_vnd") is None
    ):
        resolved_loc = stats_res.get("location") or loc_text
        msg = (
            f"Hiện tại hệ thống chưa có tin đăng phòng trọ đang hoạt động có dữ liệu giá tại khu vực {resolved_loc} "
            "để tính mức giá trung bình."
        )
        return f"<market_stats>\n{msg}\n</market_stats>\n\n", msg, "empty", []

    market_ctx_block, market_fallback = _format_market_stats_context(stats_res)
    return market_ctx_block, market_fallback, None, []


def _load_market_context_for_advisory(
    deps: Deps,
    trace: Any,
    state: dict[str, Any],
    *,
    allow_early_return: bool,
    allow_autonomous_tool: bool,
) -> tuple[str, str, Optional[dict[str, Any]]]:
    """Tra cứu số liệu thị trường cho `market-price-advisor`; trả `(ctx_block, fallback_text, optional_early_step)`."""
    skill_ctx = state.get("skill_context") or {}
    loc_text = str(skill_ctx.get("location_text") or "").strip()
    if not loc_text:
        if allow_autonomous_tool:
            return "", "", None
        msg = (
            "Bạn muốn tra cứu mặt bằng giá phòng trọ ở quận/huyện hay tỉnh/thành phố nào "
            "(ví dụ: Gò Vấp, Quận 7, Thủ Đức, Hà Nội)? Mình sẽ tra số liệu thực tế giúp bạn ngay!"
        )
        if allow_early_return:
            return "", msg, _finish_advisory_step(state, msg, needs_clarify=True)
        return f"<market_stats>\nChưa xác định được tên quận/huyện hoặc tỉnh/thành phố để tra cứu giá.\n</market_stats>\n\n", msg, None

    market_ctx_block, market_fallback, status_kind, names = _query_market_stats_for_location(
        deps,
        trace,
        loc_text,
        room_type=skill_ctx.get("room_type"),
        region_hint=skill_ctx.get("location_region"),
        location_kind=skill_ctx.get("location_kind"),
    )
    if status_kind is not None and allow_early_return:
        if status_kind == "ambiguous":
            return "", market_fallback, _finish_advisory_step(
                state,
                market_fallback,
                needs_clarify=True,
                evidence=[market_fallback],
                follow_up_questions=names,
            )
        return "", market_fallback, _finish_advisory_step(
            state,
            market_fallback,
            evidence=[market_fallback],
        )
    return market_ctx_block, market_fallback, None


def _invoke_advisory_with_market_tool(
    deps: Deps,
    trace: Any,
    model: Any,
    system: str,
    hist: list[Any],
    query: str,
    evidence: list[str],
) -> tuple[str, str]:
    """Cho phép LLM chủ động gọi `get_market_price_stats` khi NLU chưa trích được `location_text`."""
    tool_fallbacks: list[str] = []

    @lc_tool("get_market_price_stats")
    def _scoped_market_tool(location_text: str, room_type: Optional[str] = None) -> str:
        """Tra cứu thống kê giá phòng trọ thực tế (giá trung bình, min/max, số tin) theo quận/huyện hoặc tỉnh/thành phố."""
        ctx_block, fb_text, _, _ = _query_market_stats_for_location(
            deps,
            trace,
            str(location_text or "").strip(),
            room_type=room_type,
        )
        if ctx_block:
            evidence.append(ctx_block)
        if fb_text:
            evidence.append(fb_text)
            tool_fallbacks.append(fb_text)
        return ctx_block.strip() or fb_text or "Không có dữ liệu thống kê giá."

    lc_msgs: list[Any] = [SystemMessage(content=system)]
    for m in hist:
        txt = extract_message_text(m)
        lc_msgs.append(HumanMessage(content=txt) if getattr(m, "type", "") == "human" else AIMessage(content=txt))
    lc_msgs.append(HumanMessage(content=f"<user_message>\n{query}\n</user_message>"))

    bound = model.bind_tools([_scoped_market_tool])
    ai_msg = traced_call(
        trace,
        lambda: bound.invoke(lc_msgs),
        message_count=len(lc_msgs),
        node="advisory_node",
        input_data=lc_msgs,
    )
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    if not tool_calls:
        return extract_message_text(ai_msg).strip(), (tool_fallbacks[-1] if tool_fallbacks else "")

    lc_msgs.append(ai_msg)
    for tc in tool_calls[:3]:
        args = tc.get("args") or {}
        tool_out = _scoped_market_tool.invoke(args)
        lc_msgs.append(ToolMessage(content=str(tool_out), tool_call_id=str(tc.get("id") or "market_stats")))

    final_msg = traced_call(
        trace,
        lambda: model.invoke(lc_msgs),
        message_count=len(lc_msgs),
        node="advisory_node",
        input_data=lc_msgs,
    )
    return extract_message_text(final_msg).strip(), (tool_fallbacks[-1] if tool_fallbacks else "")


def make_advisory_node(deps: Deps):
    def advisory_node(state: dict[str, Any]) -> dict[str, Any]:
        slugs = _resolve_advisory_slugs(state)
        query = sanitize_user_text(state.get("user_message", ""))
        trace = resolve_trace_target(deps).sink()
        session = deps.sessions.get_or_create_session(state["session_id"]) if state.get("session_id") else None
        cached_skills = getattr(session, "consulted_skills", None) if session is not None else None

        loaded_guides: list[tuple[str, str, str]] = []
        evidence: list[str] = []
        reused_skills: list[str] = []
        for s in (slugs or [""]):
            if s and isinstance(cached_skills, dict) and s in cached_skills:
                entry = cached_skills[s]
                guide_s = str(entry.get("instructions") or "")
                refs_s = str(entry.get("references") or "")
                if guide_s:
                    reused_skills.append(s)
                    loaded_guides.append((s, guide_s, refs_s))
                    evidence.append(guide_s)
                    if refs_s:
                        evidence.append(refs_s)
                    continue
            try:
                res = tool_event(
                    trace,
                    "consult_housing_skill",
                    {"skill_name": s, "query": query},
                    lambda skill_slug=s: deps.consult_skill(skill_slug, query),
                    lambda r: {"ok": bool(r.get("ok"))},
                    node="advisory_node",
                )
            except Exception:
                res = {}
            guide_s = str(res.get("instructions") or "") if res.get("ok") else ""
            refs_s = "\n\n".join(str(v) for v in (res.get("references") or {}).values())[:MAX_REF_CHARS]
            if guide_s:
                if s and isinstance(cached_skills, dict):
                    cached_skills[s] = {"instructions": guide_s, "references": refs_s}
                loaded_guides.append((s, guide_s, refs_s))
                evidence.append(guide_s)
                if refs_s:
                    evidence.append(refs_s)

        model = deps.get_llm()
        is_multi_skill = len(slugs) > 1
        allow_auto_tool = (model is not None) and hasattr(model, "bind_tools")
        market_ctx_block = ""
        market_fallback = ""
        if MARKET_PRICE_SKILL_SLUG in slugs:
            market_ctx_block, market_fallback, early_step = _load_market_context_for_advisory(
                deps,
                trace,
                state,
                allow_early_return=not is_multi_skill,
                allow_autonomous_tool=allow_auto_tool,
            )
            if early_step is not None:
                early_step["tool_evidence"] = [*evidence, *(early_step.get("tool_evidence") or [])]
                early_step["reused_cached_skills"] = reused_skills
                return early_step
            if market_ctx_block:
                evidence.append(market_ctx_block)
            if market_fallback:
                evidence.append(market_fallback)

        if not loaded_guides or model is None:
            return _finish_advisory_step(state, market_fallback or SORRY, evidence=evidence, reused_cached_skills=reused_skills)

        skills_map = deps.skills()
        if not is_multi_skill:
            s0, guide, refs = loaded_guides[0]
            skill = skills_map.get(s0)
            label = getattr(skill, "name", s0) or s0
            system = build_advisory_prompt(s0, guide[:MAX_GUIDE_CHARS], references=refs, base_prompt=deps.base_prompt)
            labels = [label]
        else:
            system = build_multi_advisory_prompt(loaded_guides, base_prompt=deps.base_prompt)
            labels = [getattr(skills_map.get(s), "name", s) or s for s, _, _ in loaded_guides]

        hist = (
            session.compact_history_as_messages(window=4)
            if session is not None and hasattr(session, "compact_history_as_messages")
            else (session.history_as_messages(window=4) if session is not None and hasattr(session, "history_as_messages") else [])
        )
        need_auto_market_tool = (
            MARKET_PRICE_SKILL_SLUG in slugs
            and not market_ctx_block
            and allow_auto_tool
        )
        try:
            if need_auto_market_tool:
                text, tool_fb = _invoke_advisory_with_market_tool(
                    deps, trace, model, system, hist, query, evidence
                )
                if tool_fb and not market_fallback:
                    market_fallback = tool_fb
            else:
                msgs: list[tuple[str, str]] = [("system", system)]
                for m in hist:
                    role = "human" if getattr(m, "type", "") == "human" else "ai"
                    msgs.append((role, extract_message_text(m)))
                msgs.append(("human", f"{market_ctx_block}<user_message>\n{query}\n</user_message>"))
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
        elif not any((s in text or lbl in text) for s, lbl in zip([g[0] for g in loaded_guides], labels)):
            header_label = ", ".join(labels)
            text = f"💡 **Homigo AI - Tư vấn chuyên sâu ({header_label}):**\n\n{text}"
        return _finish_advisory_step(state, text, evidence=evidence, reused_cached_skills=reused_skills)

    return advisory_node
