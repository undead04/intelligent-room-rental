from __future__ import annotations

import logging
from typing import Any, Optional

from domain.enums import amenity_label
from domain.schemas import RoomItem, UserPreferenceState
from graph.deps import Deps
from graph.tracing import emit_trace, tool_event
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import sanitize_user_text
from safety.grounding import verify_context_grounding
from safety.guardrails import scan_untrusted_text
from tools.location_service import infer_region_from_preference, resolve_location
from utils.text import norm_key

logger = logging.getLogger(__name__)

RESULT_LIMIT = 5
OVERFETCH_LIMIT = 10        # có tiêu chí loại trừ -> lấy dư rồi lọc/cắt lại

_MAJOR_CITY_KEYS = ("ho chi minh", "tp hcm", "tphcm", "sai gon", "ha noi", "binh duong", "da nang")


def _infer_session_region_hint(
    pref: UserPreferenceState,
    session: Any,
    vague: dict[str, Any],
) -> Optional[str]:
    """Suy ra gợi ý tỉnh/thành (region_hint) cho địa điểm cụ thể từ ngữ cảnh lượt hiện tại hoặc lịch sử phiên."""
    explicit_region = vague.get("region")
    if explicit_region:
        return str(explicit_region)
    if pref.location_kind != "place":
        return None
    cur_loc = norm_key(pref.location_text or "")
    if any(c in cur_loc for c in _MAJOR_CITY_KEYS):
        return None

    snapshots = list(getattr(session, "turn_snapshots", []) or [])
    pref_hist = list(getattr(session, "preference_history", []) or [])
    prev_prefs = list(reversed(snapshots)) + list(reversed(pref_hist[:-1] if len(pref_hist) > 1 else []))
    for p in prev_prefs:
        hint = infer_region_from_preference(p)
        if hint:
            return hint
    return None


def synthesize_structured_query(pref: UserPreferenceState) -> str:
    """Tổng hợp câu truy vấn ngữ nghĩa chuẩn hoá từ trạng thái tích lũy UserPreferenceState."""
    parts: list[str] = []
    rt_label = pref.room_type.label_vi if pref.room_type else "Phòng trọ"
    parts.append(rt_label)
    if pref.location_text:
        parts.append(f"khu vực {pref.location_text}")
    for a in pref.amenities:
        lbl = amenity_label(a)
        if lbl and norm_key(lbl) not in norm_key(", ".join(parts)):
            parts.append(lbl)
    for a in pref.preferred_amenities:
        lbl = amenity_label(a)
        if lbl and norm_key(lbl) not in norm_key(", ".join(parts)):
            parts.append(f"ưu tiên {lbl}")
    for req in pref.special_requirements:
        if req and norm_key(req) not in norm_key(", ".join(parts)):
            parts.append(req)
    return ", ".join(parts) or "phòng trọ"


def build_query(
    pref: UserPreferenceState,
    user_text: str = "",
    semantic_query: Optional[str] = None,
) -> str:
    """Xây dựng câu truy vấn RAG theo kiến trúc Dual-Layer:
    - Lớp 1 (Ưu tiên): semantic_query do LLM viết lại tự nhiên, giàu ngữ nghĩa.
    - Lớp 2 (Dự phòng): synthesize_structured_query(pref) tự động tổng hợp từ UserPreferenceState.
    - Fallback: sanitize_user_text(user_text) nếu cả 2 lớp trên đều rỗng.
    """
    if semantic_query and len(semantic_query.strip()) >= 4:
        return sanitize_user_text(semantic_query).strip()
    has_structured = bool(
        pref.room_type
        or pref.location_text
        or pref.amenities
        or pref.preferred_amenities
        or pref.special_requirements
    )
    if has_structured:
        return synthesize_structured_query(pref)
    raw = sanitize_user_text(user_text)[:300]
    return raw or "Phòng trọ"


def make_retrieval_node(deps: Deps):
    def retrieval_node(state: dict[str, Any]) -> dict[str, Any]:
        pref = (state.get("preferences") or UserPreferenceState()).model_copy(deep=True)
        multipliers = state.get("multipliers") or {}
        weights = dict(state.get("computed_weights") or {})
        trace = list(state.get("trace_events") or [])
        retry_count = state.get("retry_count", 0)
        session = deps.sessions.get_or_create_session(state["session_id"])
        vague = state.get("vague_location_info") or {}
        status, candidates = "ok", []

        # 1) định vị
        if pref.location_text and not pref.has_point and not pref.has_admin:
            region_hint = _infer_session_region_hint(pref, session, vague)
            args = {"query": pref.location_text, "kind": pref.location_kind}
            res = tool_event(
                trace,
                "resolve_location",
                args,
                lambda: resolve_location(pref.location_text, pref.location_kind, deps.admin_lookup, deps.geocode, region_hint),
                lambda r: {"kind": r.kind, "ids": r.ids, "lat": r.lat, "lng": r.lng, "candidates": len(r.candidates)},
            )
            if res.kind == "admin":
                pref.set_location(pref.location_text, kind="admin", **res.ids)
            elif res.kind == "point":
                pref.lat, pref.lng, pref.location_kind = res.lat, res.lng, "place"
                weights = compute_normalized_weights(pref, multipliers)
            elif res.kind == "admin_not_found":
                status = "admin_not_found"
            elif res.kind == "ambiguous":
                status, candidates = "ambiguous", res.candidates
            # unresolved_point: vẫn tìm theo văn bản, không có toạ độ

        # 2) chuẩn bị tham số tìm phòng
        rooms: list[RoomItem] = []
        search_error: Optional[str] = None
        search_args: dict[str, Any] = {}
        ctx = None

        def _execute_search_and_ground(args: dict[str, Any]) -> tuple[list[RoomItem], Optional[str], Any]:
            cur_rooms: list[RoomItem] = []
            cur_err: Optional[str] = None
            call_args = dict(args)
            try:
                data = tool_event(
                    trace,
                    "search_rooms",
                    call_args,
                    lambda: deps.search_rooms(call_args),
                    lambda d: {"ok": bool(d.get("ok")), "rooms_found": len(d.get("data") or []), "error": d.get("error")},
                )
                if data.get("ok"):
                    cur_rooms = [
                        RoomItem.from_backend_result(raw, rank=i, target_lat=pref.lat, target_lng=pref.lng)
                        for i, raw in enumerate(data.get("data") or [], 1)
                    ]
                else:
                    cur_err = str(data.get("error") or "Lỗi search_rooms")
            except Exception as e:
                cur_err = str(e)

            # Lọc tin đăng chứa mã độc/injection
            safe = []
            for r in cur_rooms:
                flags = scan_untrusted_text(r.title)
                if flags:
                    logger.warning("Loại tin đăng nghi injection %s: %s", r.id, flags)
                    emit_trace(trace, "suspicious_listing", node="retrieval_node", listing_id=r.id, rules=flags)
                else:
                    safe.append(r)

            # Kiểm ràng buộc cứng + ngữ cảnh thị trường
            cur_ctx = verify_context_grounding(
                safe,
                pref,
                last_search_args=args,
                area_name=pref.location_text,
                market_fetcher=deps.market_fetcher,
            )
            return safe, cur_err, cur_ctx

        if status == "ok":
            base_radius = pref.max_distance_km or 2.5
            search_args = {
                "query": build_query(
                    pref,
                    user_text=state.get("user_message", ""),
                    semantic_query=state.get("semantic_query"),
                ),
                "lat": pref.lat,
                "lng": pref.lng,
                "min_price": pref.min_price,
                "max_price": pref.max_price,
                "min_area": pref.min_area,
                "max_area": pref.max_area,
                "amenities": [a.value for a in pref.amenities] or None,
                "preferred_amenities": [a.value for a in pref.preferred_amenities] or None,
                "max_distance_km": base_radius if pref.has_point else None,
                "weights": weights or None,
                "limit": OVERFETCH_LIMIT if pref.excluded_room_types else RESULT_LIMIT,
            }
            for key in ("city_id", "district_id", "ward_id"):
                if getattr(pref, key) is not None:
                    search_args[key] = getattr(pref, key)
            if pref.room_type is not None:
                search_args["room_type"] = pref.room_type.value
            if pref.excluded_room_types:
                search_args["excluded_room_types"] = [r.value for r in pref.excluded_room_types]

            # Pha 1: Tìm kiếm với bán kính cơ sở
            rooms, search_error, ctx = _execute_search_and_ground(search_args)

            # Pha 2: Bán kính thích ứng (Adaptive Radius) khi có tọa độ và user không cố định bán kính
            if not search_error and pref.has_point and pref.max_distance_km is None:
                for next_radius in (3.5, 5.0):
                    if len(ctx.valid_rooms) >= 3:
                        break
                    emit_trace(
                        trace,
                        "adaptive_radius_expansion",
                        node="retrieval_node",
                        from_radius=search_args.get("max_distance_km"),
                        to_radius=next_radius,
                        valid_rooms_before=len(ctx.valid_rooms),
                        reason=f"Số phòng hợp lệ ({len(ctx.valid_rooms)}) < 3, tự động mở rộng bán kính tìm kiếm lên {next_radius}km",
                    )
                    search_args["max_distance_km"] = next_radius
                    new_rooms, new_err, new_ctx = _execute_search_and_ground(search_args)
                    if not new_err:
                        rooms, search_error, ctx = new_rooms, new_err, new_ctx

        session.preferences = pref
        if search_error:
            session.proposed_budget = None
            return {
                "retrieved_rooms": [],
                "preferences": pref,
                "computed_weights": weights,
                "search_error": search_error,
                "context_grounded": False,
                "searched": False,
                "admin_not_found": False,
                "ambiguous_candidates": [],
                "trace_events": trace,
                "last_search_args": search_args,
            }

        # 4) kết luận sau tìm kiếm và phân tích thị trường
        if status == "ok" and ctx:
            rooms = ctx.valid_rooms[:RESULT_LIMIT]
            session.proposed_budget = ctx.proposed_budget
            session.zero_result_streak = 0 if rooms else session.zero_result_streak + 1
            extra = {
                "context_grounded": ctx.is_grounded,
                "proposed_budget": ctx.proposed_budget,
                "proposed_budget_str": ctx.proposed_budget_str,
                "market_context": ctx.market_context,
            }
        else:
            session.proposed_budget = None
            extra = {"context_grounded": True, "market_context": None}

        return {
            "retrieved_rooms": rooms,
            "preferences": pref,
            "computed_weights": weights,
            "search_error": None,
            "searched": True,
            "admin_not_found": status == "admin_not_found",
            "ambiguous_candidates": candidates,
            "retry_count": retry_count,
            "trace_events": trace,
            "last_search_args": search_args,
            **extra,
        }

    return retrieval_node
