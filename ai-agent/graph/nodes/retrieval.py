from __future__ import annotations

import logging
from typing import Any, Optional

from domain.enums import amenity_label
from graph.deps import Deps
from graph.tracing import tool_event
from safety.grounding import verify_context_grounding
from safety.guardrails import scan_untrusted_text
from intelligence.intent_weights import compute_normalized_weights
from tools.location_service import resolve_location
from intelligence.nlu import sanitize_user_text
from domain.schemas import RoomItem, UserPreferenceState
from utils.text import norm_key

logger = logging.getLogger(__name__)

RESULT_LIMIT = 5
OVERFETCH_LIMIT = 10        # có tiêu chí loại trừ -> lấy dư rồi lọc/cắt lại

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
    ui_action: Optional[str] = None,
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
    if has_structured or ui_action:
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
            args = {"query": pref.location_text, "kind": pref.location_kind}
            res = tool_event(trace, "resolve_location", args,
                             lambda: resolve_location(pref.location_text, pref.location_kind, deps.admin_lookup, deps.geocode, vague.get("region")),
                             lambda r: {"kind": r.kind, "ids": r.ids, "lat": r.lat, "lng": r.lng, "candidates": len(r.candidates)})
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

        # 2) tìm phòng
        rooms: list[RoomItem] = []
        search_error: Optional[str] = None
        search_args: dict[str, Any] = {}
        if status == "ok":
            search_args = {
                "query": build_query(
                    pref,
                    user_text=state.get("user_message", ""),
                    ui_action=state.get("ui_action"),
                    semantic_query=state.get("semantic_query"),
                ),
                "lat": pref.lat, "lng": pref.lng, "min_price": pref.min_price, "max_price": pref.max_price,
                "min_area": pref.min_area, "max_area": pref.max_area,
                "amenities": [a.value for a in pref.amenities] or None,
                "preferred_amenities": [a.value for a in pref.preferred_amenities] or None,
                "max_distance_km": 8.0 if pref.has_point else None,
                "weights": weights or None,
                "limit": OVERFETCH_LIMIT if pref.excluded_room_types else RESULT_LIMIT,
            }
            for key in ("city_id", "district_id", "ward_id"):
                if getattr(pref, key) is not None:
                    search_args[key] = getattr(pref, key)
            if pref.room_type is not None:
                search_args["room_type"] = pref.room_type.value
            try:
                data = tool_event(trace, "search_rooms", search_args, lambda: deps.search_rooms(search_args),
                                  lambda d: {"ok": bool(d.get("ok")), "rooms_found": len(d.get("data") or []), "error": d.get("error")})
                if data.get("ok"):
                    rooms = [RoomItem.from_backend_result(raw, rank=i, target_lat=pref.lat, target_lng=pref.lng)
                             for i, raw in enumerate(data.get("data") or [], 1)]
                else:
                    search_error = str(data.get("error") or "Lỗi search_rooms")
            except Exception as e:
                search_error = str(e)

        # 3) tin đăng chứa mã độc/injection (dữ liệu bên thứ ba) -> loại, ghi vết
        safe_rooms = []
        for r in rooms:
            flags = scan_untrusted_text(r.title)
            if flags:
                logger.warning("Loại tin đăng nghi injection %s: %s", r.id, flags)
                trace.append({"type": "suspicious_listing", "listing_id": r.id, "rules": flags})
            else:
                safe_rooms.append(r)
        rooms = safe_rooms

        session.preferences = pref
        if search_error:
            session.proposed_budget = None
            return {"retrieved_rooms": [], "preferences": pref, "computed_weights": weights, "search_error": search_error, "context_grounded": False,
                    "searched": False, "admin_not_found": False, "ambiguous_candidates": [], "trace_events": trace, "last_search_args": search_args}

        # 4) kiểm ràng buộc cứng + đề xuất HITL
        if status == "ok":
            ctx = verify_context_grounding(rooms, pref, retry_count=retry_count, last_search_args=search_args,
                                           area_name=pref.location_text, market_fetcher=deps.market_fetcher)
            rooms = ctx.valid_rooms[:RESULT_LIMIT]
            session.proposed_budget = ctx.proposed_budget
            session.hitl_streak = 0 if rooms else session.hitl_streak + 1
            extra = {"context_grounded": ctx.is_grounded, "needs_user_consent": ctx.needs_user_consent,
                     "proposed_budget": ctx.proposed_budget, "proposed_budget_str": ctx.proposed_budget_str, "hitl_proposal": ctx.hitl_proposal}
        else:
            session.proposed_budget = None
            extra = {"context_grounded": True, "needs_user_consent": False, "hitl_proposal": None}

        return {"retrieved_rooms": rooms, "preferences": pref, "computed_weights": weights, "search_error": None,
                "searched": True, "admin_not_found": status == "admin_not_found", "ambiguous_candidates": candidates,
                "retry_count": retry_count, "trace_events": trace, "last_search_args": search_args, **extra}

    return retrieval_node
