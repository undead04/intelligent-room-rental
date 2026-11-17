"""Node "hiểu lượt chat": điều phối phân tích NLU, cập nhật trạng thái tiêu chí tích lũy, và tính trọng số MCDM.

  interpret_turn(...)         hàm THUẦN: (câu, session, model) -> TurnPlan. Không ghi session.
  compute_normalized_weights  re-export từ intelligence.intent_weights để tính trọng số MCDM.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from core.config import DEFAULT_PAGE_SIZE, MAX_PAGED_ROOMS, MAX_PAGINATION_PAGES
from domain.schemas import UserPreferenceState
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import (
    CRITERIA,
    LLMQuotaExceededError,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
    is_market_only_patch,
    sanitize_user_text,
)
from utils.text import norm_key
from tools.location_service import (
    _PLACE_HINTS,
    find_poi_in_text,
    infer_region_from_location_text,
    lookup_local_poi_candidates,
)

logger = logging.getLogger(__name__)

SAFE_TEXT = {
    "PROMPT_INJECTION_DETECTED": (
        "Xin lỗi, tôi là Homigo AI - Cố vấn chuyên hỗ trợ tìm kiếm phòng trọ và nhà ở. "
        "Tôi được thiết lập để từ chối các yêu cầu can thiệp vào chỉ dẫn hệ thống. "
        "Bạn có cần tôi hỗ trợ tìm phòng trọ ở khu vực nào không?"
    ),
    "OFF_TOPIC_QUERY": (
        "Tôi là Homigo AI - Trợ lý hỗ trợ tìm kiếm phòng trọ và căn hộ. "
        "Tôi chỉ có thể hỗ trợ các câu hỏi liên quan đến chỗ ở, giá thuê và tiện ích sinh hoạt. "
        "Bạn có thể cho tôi biết bạn đang muốn tìm phòng gần trường học hay khu vực nào không?"
    ),
}


@dataclass
class TurnPlan:
    analysis: TurnAnalysis
    intent: str
    preferences: UserPreferenceState
    multipliers: dict[str, float]
    computed_weights: dict[str, float]
    weight_explanations: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    needs_budget_clarification: bool = False
    matched_skill: Optional[str] = None
    matched_skills: list[str] = field(default_factory=list)
    is_followup: bool = False
    direct_reply: bool = False          # có final_text sẵn, bỏ qua LLM trả lời -> đi thẳng formatter
    focus_rank: Optional[int] = None
    final_text: Optional[str] = None
    blocked_reason: Optional[str] = None
    vague_location_info: Optional[dict[str, Any]] = None
    skill_context: Optional[dict[str, Any]] = None
    current_task: Optional[str] = None
    pending_tasks: list[str] = field(default_factory=list)
    commit: bool = False                # True => wrapper ghi preferences/multipliers vào session
    semantic_query: Optional[str] = None
    page_switched: bool = False
    target_page: Optional[int] = None
    page_rooms: list[Any] = field(default_factory=list)


def _has_priority_change(priorities: Any) -> bool:
    return any(getattr(priorities, k, None) is not None for k in CRITERIA)


def _parse_page_navigation(
    analysis: TurnAnalysis,
    current_page: int,
    total_pages: int,
) -> Optional[int]:
    """Ánh xạ quyết định chuyển trang có cấu trúc từ LLM (`page_action`, `target_page`) sang số trang mục tiêu."""
    if total_pages <= 0:
        return None
    if not analysis.patch.is_empty() or analysis.reset_priorities or _has_priority_change(analysis.priorities):
        return None
    if analysis.referenced_room_rank is not None or analysis.intent in ("room_followup", "skill_advice", "prompt_injection", "off_topic"):
        return None

    action = getattr(analysis, "page_action", None)
    if not action:
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


def _format_page_switch_reply(page_rooms: list[Any], page: int, total_pages: int, total_rooms: int) -> str:
    """Dựng văn bản xác định từ dữ liệu thật của 5 phòng thuộc trang `page`."""
    if not page_rooms:
        return "Hiện không có dữ liệu phòng ở trang này."
    start_rank = getattr(page_rooms[0], "rank", (page - 1) * DEFAULT_PAGE_SIZE + 1)
    end_rank = getattr(page_rooms[-1], "rank", start_rank + len(page_rooms) - 1)
    lines = [
        f"Mình đã chuyển sang **Trang {page}/{total_pages}** (hiển thị phòng **Top {start_rank}–{end_rank}** trong tổng số **{total_rooms} phòng** phù hợp):",
        "",
    ]
    for r in page_rooms:
        meta = [f"Giá: {r.price}"]
        if getattr(r, "area_m2", None):
            meta.append(f"{r.area_m2:g} m²")
        if getattr(r, "distance", ""):
            meta.append(f"cách {r.distance}")
        lines.append(f"- **Top {r.rank}. {r.title}** ({' | '.join(meta)})")
    lines.extend([
        "",
        "Bạn có thể bấm trực tiếp số trang `1..10` ở danh sách bên cạnh, click vào phòng để xem phân tích chi tiết hoặc hỏi mình về bất kỳ **Top N** nào nhé!",
    ])
    return "\n".join(lines)


def _active_skills(analysis: TurnAnalysis) -> list[str]:
    slugs = [str(s).strip() for s in (getattr(analysis, "skill_slugs", None) or []) if str(s or "").strip()]
    single = str(getattr(analysis, "skill_slug", None) or "").strip()
    if single and single not in slugs:
        slugs.insert(0, single) if not slugs else slugs.append(single)
    return list(dict.fromkeys(slugs))


def _build_skill_context(
    analysis: TurnAnalysis,
    pref: UserPreferenceState,
    active_skills: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Tạo ngữ cảnh riêng cho skill cần tra cứu theo địa danh (không ghi đè session.preferences)."""
    skills_list = active_skills if active_skills is not None else _active_skills(analysis)
    if "market-price-advisor" not in skills_list:
        return None
    loc_text = (analysis.patch.location_text or "").strip() or None
    loc_kind = analysis.patch.location_kind
    loc_region = (analysis.patch.location_region or "").strip() or None
    if not loc_text and pref.location_text:
        loc_text = pref.location_text
        loc_kind = pref.location_kind
    room_type = (
        analysis.patch.allowed_room_types[0].value
        if len(analysis.patch.allowed_room_types) == 1
        else None
    )
    return {
        "location_text": loc_text,
        "location_kind": loc_kind,
        "location_region": loc_region,
        "room_type": room_type,
    }


def _rooms_brief(rooms: list) -> str:
    return "; ".join(f"Top {r.rank}: {r.title} ({r.price})" for r in rooms[:5])


def _plan_multi_intent_order(
    analysis: TurnAnalysis,
    *,
    has_followup: bool,
    has_search: bool,
    has_advisory: bool,
    has_old_rooms: bool,
) -> list[str]:
    """Điều phối danh sách tác vụ đa mệnh lệnh theo `analysis.task_order` do LLM trả (có bảo toàn workflow)."""
    active: list[str] = []
    if has_search:
        active.append("search")
    if has_followup:
        active.append("followup")
    if has_advisory:
        active.append("advisory")

    raw_order = [t for t in (getattr(analysis, "task_order", None) or []) if t in active]
    ordered = list(dict.fromkeys(raw_order))

    if len(ordered) < len(active):
        # Đặt nhánh chính (intent) lên trước các nhánh còn lại nếu LLM không liệt kê đủ task_order
        primary = (
            "followup" if analysis.intent == "room_followup"
            else ("advisory" if analysis.intent == "skill_advice" else "search")
        )
        if primary in active and primary not in ordered:
            ordered.append(primary)
        for t in ("search", "followup", "advisory"):
            if t in active and t not in ordered:
                ordered.append(t)

    if "followup" in ordered:
        search_before_followup = ("search" in ordered) and (ordered.index("search") < ordered.index("followup"))
        if not has_old_rooms and not search_before_followup:
            ordered.remove("followup")

    return ordered


def _build_multi_intent_reply(
    analysis: TurnAnalysis,
    skills: Optional[dict[str, Any]],
    has_patch: bool,
) -> str:
    """Sinh đoạn hội thoại tự nhiên khi người dùng nhập gộp nhiều mệnh lệnh khác nhánh trong cùng 1 lượt."""
    skill_desc = "cẩm nang thuê trọ"
    if analysis.skill_slug and skills and analysis.skill_slug in skills:
        meta = skills[analysis.skill_slug]
        skill_desc = (getattr(meta, "description", "") or getattr(meta, "name", "") or skill_desc).strip().rstrip(".")

    rank_str = f"phòng Top {analysis.referenced_room_rank}" if analysis.referenced_room_rank else "phòng đã đề xuất"

    if has_patch and analysis.skill_slug:
        return (
            "Homigo thấy bạn đang yêu cầu nhiều việc cùng lúc. Mình đã ghi nhận sẵn các tiêu chí tìm phòng của bạn vào bộ nhớ rồi nhé! "
            "Để thông tin phản hồi rõ ràng và không bị quá tải, Homigo sẽ hỗ trợ bạn giải quyết từng yêu cầu một. "
            f"Bạn nhắn cho mình biết bạn muốn tìm danh sách phòng trọ trước hay muốn tư vấn về {skill_desc.lower()} trước nha?"
        )
    if has_patch and (analysis.referenced_room_rank is not None or analysis.intent == "room_followup"):
        return (
            f"Homigo thấy bạn vừa hỏi chi tiết về {rank_str}, vừa đưa thêm tiêu chí tìm phòng mới. "
            "Mình đã lưu sẵn các tiêu chí mới của bạn vào bộ nhớ rồi nhé! Để tránh nhầm lẫn dữ liệu giữa phòng hiện tại và lượt tìm kiếm mới, "
            f"bạn nhắn cho mình biết bạn muốn xem chi tiết {rank_str} trước hay chạy tìm kiếm phòng mới trước nha?"
        )
    return (
        f"Homigo thấy bạn vừa muốn kiểm tra chi tiết {rank_str}, vừa muốn hỏi về {skill_desc.lower()}. "
        "Để mình giải đáp sâu và chi tiết từng phần, bạn nhắn cho Homigo biết bạn muốn xem thông tin chi tiết của "
        f"{rank_str} trước hay tư vấn {skill_desc.lower()} trước nhé!"
    )


def _build_revert_preferences(
    base_pref: UserPreferenceState,
    analysis: TurnAnalysis,
    current_pref: UserPreferenceState,
) -> UserPreferenceState:
    """Tái tạo tiêu chí khi người dùng quay lại lượt chat trước hoặc ban đầu, áp thêm thay đổi mới từ patch của LLM."""
    incremental_patch = analysis.patch.model_copy(deep=True)
    incremental_patch.clear = []
    pref = apply_patch(base_pref, incremental_patch)

    if analysis.semantic_query and current_pref.location_text:
        cur_loc = current_pref.location_text.lower()
        base_loc = (base_pref.location_text or "").lower()
        if cur_loc in analysis.semantic_query.lower() and cur_loc not in base_loc:
            analysis.semantic_query = None

    return pref


def _match_pending_ambiguous_candidate(
    user_text: str,
    patch_location: Optional[str],
    pending_cands: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Khớp lựa chọn của user với 1 ứng viên trong danh sách ambiguous vừa hỏi (theo số nút UI 1..5 hoặc tên riêng)."""
    if not pending_cands:
        return None

    clean_u = norm_key(sanitize_user_text(user_text))
    # 1. Chọn trực tiếp theo chỉ số phương án UI (vd: '1', '2', ...)
    if clean_u.isdigit():
        idx = int(clean_u) - 1
        if 0 <= idx < len(pending_cands):
            return pending_cands[idx]

    # 2. Khớp theo tên ứng viên (vd bấm chip follow-up hoặc gõ đúng 1 ứng viên duy nhất)
    probes = [p for p in (norm_key(patch_location or ""), clean_u) if p and len(p) >= 2]
    for probe in probes:
        exact_hits = [c for c in pending_cands if norm_key(str(c.get("name") or "")) == probe]
        if len(exact_hits) == 1:
            return exact_hits[0]
        # Trường hợp user bấm chip bị cắt bởi '...' hoặc gõ phân đoạn đủ dài của tên/địa chỉ
        partial_hits = []
        for c in pending_cands:
            c_name = norm_key(str(c.get("name") or ""))
            c_addr = norm_key(str(c.get("address") or ""))
            if not c_name:
                continue
            if (len(probe) >= 4 and (probe in c_name or probe in c_addr)) or (
                len(c_name) >= 4 and c_name in probe
            ):
                partial_hits.append(c)
        if len(partial_hits) == 1:
            return partial_hits[0]
    return None


def interpret_turn(
    user_text: str,
    session: Any,
    model: Any,
    *,
    retry_model: Any = None,
    skills: Optional[dict[str, Any]] = None,
) -> TurnPlan:
    pref0: UserPreferenceState = session.preferences
    mult0 = {k: float((session.multipliers or {}).get(k, 1.0)) for k in CRITERIA}
    rooms = list(session.last_rooms or [])
    paged_pool = list(getattr(session, "paged_rooms", None) or rooms)[:MAX_PAGED_ROOMS]
    has_history = bool(rooms or paged_pool or session.messages)

    recent_dialog_turns = session.compact_history_tuples(window=4) if hasattr(session, "compact_history_tuples") else None
    recent_user_turns = [text for role, text in (getattr(session, "history", None) or []) if role == "user"][-3:]
    page_info = ""
    if paged_pool:
        ps = max(1, int(getattr(session, "page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE))
        cp = max(1, int(getattr(session, "current_page", 1) or 1))
        tp = min(MAX_PAGINATION_PAGES, max(1, math.ceil(len(paged_pool) / ps)))
        page_info = f"Trang {cp}/{tp} (tổng {len(paged_pool)} phòng)"
    pending_loc_ctx = str(getattr(session, "pending_ambiguous_location", None) or "")
    try:
        analysis = analyze_turn(
            model,
            user_text,
            pref0,
            retry_model=retry_model,
            rooms_brief=_rooms_brief(rooms),
            multipliers=mult0,
            n_rooms=len(paged_pool) if paged_pool else len(rooms),
            skills=skills,
            recent_dialog_turns=recent_dialog_turns,
            recent_user_turns=recent_user_turns,
            page_info=page_info,
            pending_location=pending_loc_ctx,
        )
    except LLMQuotaExceededError:
        logger.warning("interpret_turn: LLM cạn Quota (429 RESOURCE_EXHAUSTED), kích hoạt phản hồi cảnh báo Quota trực tiếp.")
        quota_text = (
            "⚠️ **Hạn mức sử dụng AI tạm thời bị gián đoạn (Quota Exceeded / 429)**\n\n"
            "Mô hình AI hiện tại đã đạt giới hạn lượt gọi miễn phí trong ngày của API Key "
            "(Google Gemini Free Tier Quota Exceeded — 500 requests/ngày).\n\n"
            "💡 **Cách khắc phục:**\n"
            "1. Cập nhật `OPENAI_API_KEY` mới trong file `ai-agent/.env` (tạo miễn phí tại [Google AI Studio](https://aistudio.google.com/)).\n"
            "2. Hoặc khởi động lại dịch vụ sau khi hạn mức được Google làm mới (sau khoảng 6 tiếng)."
        )
        empty_analysis = TurnAnalysis(intent="smalltalk")
        return TurnPlan(
            analysis=empty_analysis,
            intent="smalltalk",
            preferences=pref0,
            multipliers=mult0,
            computed_weights=compute_normalized_weights(pref0, mult0),
            direct_reply=True,
            final_text=quota_text,
            needs_clarification=False,
        )

    if analysis is None:
        # Không có model hoặc LLM lỗi: không dùng regex đoán mò, yêu cầu làm rõ an toàn
        empty_analysis = TurnAnalysis(intent="smalltalk")
        return TurnPlan(
            analysis=empty_analysis,
            intent="smalltalk",
            preferences=pref0,
            multipliers=mult0,
            computed_weights=compute_normalized_weights(pref0, mult0),
            needs_clarification=True,
        )

    def plan(**kw: Any) -> TurnPlan:
        pref = kw.pop("preferences", pref0)
        mult = kw.pop("multipliers", mult0)
        sem_q = kw.pop("semantic_query", getattr(analysis, "semantic_query", None))
        return TurnPlan(
            analysis=analysis,
            intent=analysis.intent,
            preferences=pref,
            multipliers=mult,
            computed_weights=compute_normalized_weights(pref, mult),
            semantic_query=sem_q,
            **kw,
        )

    intent = analysis.intent

    # 1) Chặn: injection / off-topic
    if intent in ("prompt_injection", "off_topic"):
        reason = "PROMPT_INJECTION_DETECTED" if intent == "prompt_injection" else "OFF_TOPIC_QUERY"
        return plan(blocked_reason=reason, final_text=SAFE_TEXT[reason])

    # 1.2) Chuyển trang trên danh sách đã tìm (0 gọi Backend, 0 tốn LLM Decision)
    if paged_pool:
        page_size = max(1, int(getattr(session, "page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE))
        cur_page = max(1, int(getattr(session, "current_page", 1) or 1))
        total_pages = min(MAX_PAGINATION_PAGES, max(1, math.ceil(len(paged_pool) / page_size)))
        req_page = _parse_page_navigation(analysis, cur_page, total_pages)
        if req_page is not None:
            if 1 <= req_page <= total_pages:
                start = (req_page - 1) * page_size
                target_rooms = paged_pool[start : start + page_size]
                return plan(
                    direct_reply=True,
                    page_switched=True,
                    target_page=req_page,
                    page_rooms=target_rooms,
                    final_text=_format_page_switch_reply(target_rooms, req_page, total_pages, len(paged_pool)),
                )
            cur_start = (cur_page - 1) * page_size
            cur_rooms = paged_pool[cur_start : cur_start + page_size]
            if req_page > total_pages:
                msg = (
                    f"Hiện tại chỉ có tổng cộng **{len(paged_pool)} phòng** (**{total_pages} trang**) phù hợp với bộ lọc của bạn "
                    f"(bạn đang xem đến hết Trang {cur_page}/{total_pages}). "
                    "Nếu chưa chọn được phòng ưng ý, bạn có thể nhắn mình nới nhẹ ngân sách, bán kính hoặc bỏ bớt tiện ích bắt buộc để tìm thêm nhé!"
                )
            else:
                msg = f"Bạn đang ở **Trang 1/{total_pages}** rồi, không thể lùi về trang trước đó nữa."
            return plan(
                direct_reply=True,
                page_switched=False,
                target_page=cur_page,
                page_rooms=cur_rooms,
                final_text=msg,
            )

    # 1.5) Lập kế hoạch thực thi tuần tự cho Đa Mệnh Lệnh (Plan & Execute):
    # Sắp xếp tự do theo đúng thứ tự mệnh đề user yêu cầu (hỗ trợ mọi hoán vị followup / search / advisory).
    active_skills = _active_skills(analysis)
    multi_tasks: list[str] = []
    multi_has_followup = False
    multi_has_search = False
    multi_has_advisory = False
    if getattr(analysis, "is_multi_intent", False):
        followup_requested = (analysis.referenced_room_rank is not None or intent == "room_followup")
        multi_has_advisory = bool(active_skills)
        multi_has_search = (
            (not analysis.patch.is_empty() and not is_market_only_patch(analysis, active_skills))
            or ("search" in (getattr(analysis, "task_order", None) or []))
            or (intent in ("new_search", "refine_search") and not followup_requested and not multi_has_advisory)
        )
        multi_tasks = _plan_multi_intent_order(
            analysis,
            has_followup=followup_requested,
            has_search=multi_has_search,
            has_advisory=multi_has_advisory,
            has_old_rooms=bool(rooms),
        )
        multi_has_followup = "followup" in multi_tasks

        if multi_tasks and not multi_has_search:
            focus_rank = (
                analysis.referenced_room_rank
                if analysis.referenced_room_rank is not None
                else (getattr(session, "focused_room_rank", None) or 1)
            )
            return plan(
                matched_skill=active_skills[0] if (multi_has_advisory and active_skills) else None,
                matched_skills=active_skills if multi_has_advisory else [],
                skill_context=_build_skill_context(analysis, pref0, active_skills=active_skills) if multi_has_advisory else None,
                is_followup=(multi_tasks[0] == "followup"),
                focus_rank=focus_rank if multi_has_followup else None,
                current_task=multi_tasks[0],
                pending_tasks=multi_tasks[1:],
            )

    # 2) Hỏi tiếp về phòng đã đề xuất
    if intent == "room_followup" and not multi_tasks:
        if not rooms and not paged_pool:
            # Chưa có phòng nào được đề xuất trong phiên -> chuyển sang hỏi làm rõ nhu cầu
            return plan(needs_clarification=True)
        if analysis.referenced_room_rank is not None:
            current_focus = analysis.referenced_room_rank
        elif getattr(analysis, "followup_current_page_first", False) and rooms:
            current_focus = getattr(rooms[0], "rank", 1)
        else:
            current_focus = getattr(session, "focused_room_rank", None) or (getattr(rooms[0], "rank", 1) if rooms else 1)
        return plan(is_followup=True, focus_rank=current_focus)

    # 3) Tư vấn kỹ năng
    if intent == "skill_advice" and not multi_tasks:
        return plan(
            matched_skill=active_skills[0] if active_skills else None,
            matched_skills=active_skills,
            skill_context=_build_skill_context(analysis, pref0, active_skills=active_skills),
        )

    # 4) Chào hỏi / mơ hồ -> để clarification_node trả lời
    if intent == "smalltalk":
        return plan(needs_clarification=True)

    # 5) Tìm mới / chỉnh tiêu chí
    explanations: list[str] = []
    pref, mult = pref0, mult0
    commit = True

    history_snapshots = getattr(session, "preference_history", []) or []
    revert_mode = getattr(analysis, "revert_mode", None)
    target_turn_num = getattr(analysis, "revert_turn", None)
    is_revert_explicit_turn = (revert_mode == "turn") and isinstance(target_turn_num, int)
    is_revert_initial = (revert_mode == "initial") or (is_revert_explicit_turn and target_turn_num == 1)
    is_revert_previous = revert_mode == "previous"

    base_pref = pref0
    turn_snaps = getattr(session, "turn_snapshots", []) or []
    if is_revert_explicit_turn and target_turn_num and 1 <= target_turn_num <= len(turn_snaps):
        base_pref = turn_snaps[target_turn_num - 1].model_copy(deep=True)
        pref = _build_revert_preferences(base_pref, analysis, pref0)
        mult = {k: 1.0 for k in CRITERIA}
        explanations.append(f"đã quay lại tiêu chí của lượt chat thứ {target_turn_num} theo yêu cầu")
    elif is_revert_explicit_turn and target_turn_num and target_turn_num > len(turn_snaps):
        if turn_snaps:
            pref = turn_snaps[-1].model_copy(deep=True)
            explanations.append(f"phiên hiện có {len(turn_snaps)} lượt tìm kiếm, giữ tiêu chí gần nhất")
        elif getattr(session, "initial_preference", None):
            pref = session.initial_preference.model_copy(deep=True)
            explanations.append("giữ tiêu chí tìm kiếm ban đầu")
        else:
            pref = pref0
    elif is_revert_initial and (getattr(session, "initial_preference", None) or history_snapshots or turn_snaps):
        base_pref = (
            session.initial_preference.model_copy(deep=True)
            if getattr(session, "initial_preference", None)
            else history_snapshots[0].model_copy(deep=True)
        )
        pref = _build_revert_preferences(base_pref, analysis, pref0)
        mult = {k: 1.0 for k in CRITERIA}
        explanations.append("đã quay lại tiêu chí ban đầu theo yêu cầu")
    elif is_revert_previous and history_snapshots:
        target = history_snapshots[-2] if len(history_snapshots) >= 2 else history_snapshots[0]
        base_pref = target.model_copy(deep=True)
        pref = _build_revert_preferences(base_pref, analysis, pref0)
        explanations.append("đã quay lại tiêu chí trước đó theo yêu cầu")
    else:
        pref = apply_patch(base_pref, analysis.patch)
        mult = apply_priorities(mult0, analysis.priorities, reset=analysis.reset_priorities)

        # Kết hợp lại với địa danh đang hỏi dở (ambiguous) nếu lượt này user chọn 1 ứng viên hoặc trả lời ngắn quận/tỉnh/cơ sở
        pending_loc = getattr(session, "pending_ambiguous_location", None)
        pending_cands = list(getattr(session, "pending_ambiguous_candidates", []) or [])
        is_pivot = bool(getattr(analysis, "is_location_pivot", False))
        matched_cand = (
            _match_pending_ambiguous_candidate(user_text, analysis.patch.location_text, pending_cands)
            if (pending_cands and not is_pivot)
            else None
        )
        if matched_cand is not None:
            cand_name = str(matched_cand.get("name") or pending_loc or user_text).strip()
            if matched_cand.get("lat") is not None and matched_cand.get("lng") is not None:
                pref.set_location(cand_name, kind="place")
                pref.lat = float(matched_cand["lat"])
                pref.lng = float(matched_cand["lng"])
                explanations.append(f"chọn đúng tọa độ ứng viên '{cand_name}' từ danh sách gợi ý")
            elif pending_loc and norm_key(pending_loc) not in norm_key(cand_name):
                pref.set_location(f"{pending_loc}, {cand_name}", kind="place")
                explanations.append(f"ghép '{pending_loc}' với lựa chọn '{cand_name}'")
            else:
                pref.set_location(cand_name, kind="admin" if matched_cand.get("level") else None)
                explanations.append(f"chọn ứng viên '{cand_name}' từ danh sách gợi ý")
        elif pending_loc and not is_pivot:
            new_loc = (analysis.patch.location_text or "").strip()
            loc_region = (analysis.patch.location_region or "").strip()
            if new_loc and norm_key(pending_loc) not in norm_key(new_loc):
                looks_modifier = (
                    analysis.patch.location_kind == "admin"
                    or bool(infer_region_from_location_text(new_loc))
                )
                if looks_modifier and not _PLACE_HINTS.search(new_loc):
                    pref.set_location(f"{pending_loc}, {new_loc}", kind="place")
                    explanations.append(f"ghép địa điểm đang làm rõ '{pending_loc}' với '{new_loc}'")
            elif not new_loc and loc_region:
                pref.set_location(f"{pending_loc}, {loc_region}", kind="place")
                explanations.append(f"ghép địa điểm đang làm rõ '{pending_loc}' với '{loc_region}'")
    explanations.extend([r for r in analysis.priority_reasons if r][:3])

    is_vague_loc = bool(analysis.patch.location_is_vague)
    if is_vague_loc:
        if pref.has_point:
            is_vague_loc = False
        else:
            # Nếu LLM lỡ đánh nhầm địa danh có tên riêng (vd 'KCN Amata Biên Hòa') là location_is_vague -> giải cứu sang tìm kiếm ngay
            patch_loc = (analysis.patch.location_text or "").strip()
            if patch_loc and (
                lookup_local_poi_candidates(patch_loc, analysis.patch.location_region)
                or analysis.patch.location_kind == "place"
            ):
                pref.set_location(patch_loc, kind=analysis.patch.location_kind or "place")
                is_vague_loc = False
            elif pref.location_text and (
                lookup_local_poi_candidates(pref.location_text, analysis.patch.location_region)
                or analysis.patch.location_kind == "place"
            ):
                is_vague_loc = False
            else:
                matched_poi = find_poi_in_text(user_text, analysis.patch.location_region)
                if matched_poi:
                    pref.set_location(matched_poi, kind="place")
                    is_vague_loc = False
                elif analysis.patch.vague_category and lookup_local_poi_candidates(
                    analysis.patch.vague_category, analysis.patch.location_region
                ):
                    pref.set_location(analysis.patch.vague_category, kind="place")
                    is_vague_loc = False

    vague_info = None
    if is_vague_loc:
        vague_info = {"category": analysis.patch.vague_category, "region": analysis.patch.location_region}
    elif analysis.patch.location_region:
        vague_info = {"category": None, "region": analysis.patch.location_region}

    has_loc = bool(pref.location_text or pref.has_point or pref.district_id or pref.city_id)
    needs_budget_clarify = bool(getattr(analysis, "needs_budget_clarification", False))
    if is_vague_loc or needs_budget_clarify or not has_loc:
        needs_clarify = True
    else:
        needs_clarify = False

    if multi_tasks:
        followup_after_search = (
            "search" in multi_tasks
            and "followup" in multi_tasks
            and multi_tasks.index("search") < multi_tasks.index("followup")
        )
        focus_rank = (
            (
                analysis.referenced_room_rank
                if analysis.referenced_room_rank is not None
                else (1 if followup_after_search else (getattr(session, "focused_room_rank", None) or 1))
            )
            if multi_has_followup
            else None
        )
        return plan(
            preferences=pref,
            multipliers=mult,
            weight_explanations=explanations,
            needs_clarification=needs_clarify,
            needs_budget_clarification=needs_budget_clarify,
            vague_location_info=vague_info,
            matched_skill=active_skills[0] if (multi_has_advisory and active_skills) else None,
            matched_skills=active_skills if multi_has_advisory else [],
            skill_context=_build_skill_context(analysis, pref, active_skills=active_skills) if multi_has_advisory else None,
            is_followup=(multi_tasks[0] == "followup"),
            focus_rank=focus_rank,
            current_task=multi_tasks[0],
            pending_tasks=multi_tasks[1:],
            commit=commit,
        )

    return plan(
        preferences=pref,
        multipliers=mult,
        weight_explanations=explanations,
        needs_clarification=needs_clarify,
        needs_budget_clarification=needs_budget_clarify,
        vague_location_info=vague_info,
        commit=commit,
    )


__all__ = [
    "SAFE_TEXT",
    "TurnPlan",
    "compute_normalized_weights",
    "interpret_turn",
]
