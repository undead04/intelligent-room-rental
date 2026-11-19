"""Logic điều phối phân trang theo `offset` trên danh sách `paged_rooms` đã lưu trong session."""

from __future__ import annotations

import math
from typing import Any, Optional

from core.config import DEFAULT_PAGE_SIZE, MAX_PAGINATION_PAGES
from domain.enums import RoomType
from domain.schemas import UserPreferenceState
from intelligence.insights import build_decision_insights
from intelligence.nlu import CRITERIA, PreferencePatch, TurnAnalysis
from utils.text import norm_key


def _has_priority_change(priorities: Any) -> bool:
    return any(getattr(priorities, k, None) is not None for k in CRITERIA)


def _has_active_skills(analysis: TurnAnalysis) -> bool:
    has_list = any(str(s or "").strip() for s in (getattr(analysis, "skill_slugs", None) or []))
    has_single = bool(str(getattr(analysis, "skill_slug", None) or "").strip())
    return has_list or has_single


def is_effective_patch_empty_for_pagination(
    patch: PreferencePatch,
    current_pref: UserPreferenceState,
) -> bool:
    """True nếu patch rỗng hoặc chỉ lặp lại tiêu chí hiện có / loại phòng mặc định khi chuyển trang."""
    if patch.is_empty():
        return True
    if (
        patch.clear
        or patch.location_is_vague
        or patch.vague_category
        or patch.amenities_remove
        or patch.special_requirements_remove
    ):
        return False
    if patch.location_text:
        if not current_pref.location_text or norm_key(patch.location_text) != norm_key(current_pref.location_text):
            return False
    elif patch.location_region:
        if not current_pref.location_text or norm_key(patch.location_region) not in norm_key(current_pref.location_text):
            return False
    for key in ("max_distance_km", "min_price", "max_price", "min_area", "max_area", "min_bedrooms"):
        val = getattr(patch, key)
        if val is not None and val != getattr(current_pref, key):
            return False
    if patch.amenities_add and any(a not in current_pref.amenities for a in patch.amenities_add):
        return False
    existing_soft = set(current_pref.amenities) | set(current_pref.preferred_amenities)
    if patch.preferred_amenities_add and any(a not in existing_soft for a in patch.preferred_amenities_add):
        return False
    existing_specs = {norm_key(s) for s in current_pref.special_requirements}
    if patch.special_requirements_add and any(norm_key(s) not in existing_specs for s in patch.special_requirements_add):
        return False
    if patch.allowed_room_types:
        if set(patch.allowed_room_types) != set(current_pref.allowed_room_types):
            if not (not current_pref.allowed_room_types and patch.allowed_room_types == [RoomType.ROOM]):
                return False
    if patch.excluded_room_types:
        if not set(patch.excluded_room_types).issubset(set(current_pref.excluded_room_types)):
            if not (not current_pref.excluded_room_types and patch.excluded_room_types == [RoomType.SLEEPBOX]):
                return False
    return True


def parse_page_navigation(
    analysis: TurnAnalysis,
    current_page: int,
    total_pages: int,
    current_pref: Optional[UserPreferenceState] = None,
) -> Optional[int]:
    """Ánh xạ quyết định chuyển trang có cấu trúc từ LLM (`page_action`, `target_page`) sang số trang mục tiêu."""
    if total_pages <= 0:
        return None
    action = getattr(analysis, "page_action", None)
    if not action:
        if analysis.intent == "page_navigation":
            action = "next"
        else:
            return None
    if getattr(analysis, "is_multi_intent", False):
        return None
    if not is_effective_patch_empty_for_pagination(analysis.patch, current_pref or UserPreferenceState()):
        return None
    if _has_priority_change(analysis.priorities):
        return None
    if (
        analysis.referenced_room_rank is not None
        or getattr(analysis, "followup_current_page_first", False)
        or _has_active_skills(analysis)
        or analysis.intent in ("skill_advice", "prompt_injection", "off_topic")
    ):
        return None
    if analysis.intent == "room_followup" and (
        analysis.referenced_room_rank is not None or getattr(analysis, "followup_current_page_first", False)
    ):
        return None

    if action == "goto":
        tp = getattr(analysis, "target_page", None)
        return int(tp) if isinstance(tp, int) and tp >= 1 else None
    if action == "first":
        return 1
    if action == "last":
        return total_pages
    if action == "next":
        return current_page + 1
    if action == "prev":
        return current_page - 1
    return None


def plan_page_navigation(
    analysis: TurnAnalysis,
    session: Any,
    pref0: UserPreferenceState,
    paged_pool: list[Any],
) -> Optional[dict[str, Any]]:
    """Tính `offset` từ trang mục tiêu và cắt lát `paged_pool[offset : offset + page_size]` đưa vào `decision_node`."""
    if paged_pool:
        page_size = max(1, int(getattr(session, "page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE))
        cur_page = max(1, int(getattr(session, "current_page", 1) or 1))
        total_pages = min(MAX_PAGINATION_PAGES, max(1, math.ceil(len(paged_pool) / page_size)))
        req_page = parse_page_navigation(analysis, cur_page, total_pages, current_pref=pref0)
        if req_page is None:
            return None

        analysis.patch = PreferencePatch()
        analysis.reset_priorities = False
        analysis.semantic_query = None
        analysis.needs_budget_clarification = False

        if 1 <= req_page <= total_pages:
            offset = (req_page - 1) * page_size
            target_rooms = paged_pool[offset : offset + page_size]
            page_insights = build_decision_insights(target_rooms)
            return {
                "intent": "page_navigation",
                "direct_reply": False,
                "semantic_query": None,
                "page_switched": True,
                "target_page": req_page,
                "page_rooms": target_rooms,
                "insights": page_insights,
            }

        cur_offset = (cur_page - 1) * page_size
        cur_rooms = paged_pool[cur_offset : cur_offset + page_size]
        if req_page > total_pages:
            msg = (
                f"Hiện tại chỉ có tổng cộng **{len(paged_pool)} phòng** (**{total_pages} trang**) phù hợp với bộ lọc của bạn "
                f"(bạn đang xem đến hết Trang {cur_page}/{total_pages}). "
                "Nếu chưa chọn được phòng ưng ý, bạn có thể nhắn mình nới nhẹ ngân sách, bán kính hoặc bỏ bớt tiện ích bắt buộc để tìm thêm nhé!"
            )
        else:
            msg = f"Bạn đang ở **Trang 1/{total_pages}** rồi, không thể lùi về trang trước đó nữa."
        return {
            "intent": "page_navigation",
            "direct_reply": True,
            "semantic_query": None,
            "page_switched": False,
            "target_page": cur_page,
            "page_rooms": cur_rooms,
            "final_text": msg,
        }

    if (
        (getattr(analysis, "page_action", None) or analysis.intent == "page_navigation")
        and not getattr(analysis, "is_multi_intent", False)
        and is_effective_patch_empty_for_pagination(analysis.patch, pref0)
        and not _has_priority_change(analysis.priorities)
        and analysis.referenced_room_rank is None
        and not getattr(analysis, "followup_current_page_first", False)
        and not _has_active_skills(analysis)
    ):
        return {
            "intent": "page_navigation",
            "direct_reply": True,
            "semantic_query": None,
            "needs_clarification": True,
            "final_text": (
                "Hiện tại chưa có danh sách phòng nào trong phiên để chuyển trang. "
                "Bạn hãy cho Homigo biết khu vực và ngân sách muốn tìm phòng trước nhé!"
            ),
        }
    return None


__all__ = [
    "is_effective_patch_empty_for_pagination",
    "parse_page_navigation",
    "plan_page_navigation",
]
