"""Node "hiểu lượt chat": thay preference_intent_node (+ guardrail lớp 2, + nhận diện skill).

  interpret_turn(...)       hàm THUẦN: (câu, session, model) -> TurnPlan. Không ghi session. Test được bằng SimpleNamespace.
  understand_turn_node(...) wrapper LangGraph: là NƠI DUY NHẤT ghi session.preferences / session.multipliers.
  route_after_understand    thay route_after_preference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from domain.budget import round_up_step, tighten_budget
from domain.enums import HitlAction, RoomType
from domain.schemas import UserPreferenceState, format_vnd_million
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import (
    CRITERIA,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
)
from intelligence.nlu_fallback import legacy_analysis

logger = logging.getLogger(__name__)

# Các con số HITL gom một chỗ (trước đây rải ở graph: 1.15 / 1.5 / 1.8 / 3_000_000)
HITL_TUNING = {
    "relax_budget_factor": 1.15,
    "relax_price_mult": 1.5,
    "dormitory_price_mult": 1.8,
    "default_budget": 3_000_000.0,
}

KEEP_TEXT = "Dạ Homigo đã ghi nhận bạn muốn giữ nguyên các tiêu chí ban đầu. Khi có phòng mới phù hợp, Homigo sẽ cập nhật ngay nhé!"
CUSTOM_TEXT = "Bạn có thể nhập trực tiếp tiêu chí muốn điều chỉnh (khu vực, giá, tiện ích) để Homigo tìm kiếm lại nhé!"
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
    matched_skill: Optional[str] = None
    is_followup: bool = False
    is_keep: bool = False
    direct_reply: bool = False          # có final_text sẵn, bỏ qua LLM trả lời -> đi thẳng formatter
    focus_rank: Optional[int] = None
    final_text: Optional[str] = None
    blocked_reason: Optional[str] = None
    vague_location_info: Optional[dict[str, Any]] = None
    used_fallback: bool = False
    commit: bool = False                # True => wrapper ghi preferences/multipliers vào session
    semantic_query: Optional[str] = None
    reset_hitl: bool = False


def _as_action(v: Any) -> Optional[HitlAction]:
    if v is None or v == "":
        return None
    try:
        return v if isinstance(v, HitlAction) else HitlAction(str(v).strip().lower())
    except ValueError:
        logger.warning("ui_action lạ: %r", v)
        return None


def _rooms_brief(rooms: list) -> str:
    return "; ".join(f"Top {r.rank}: {r.title} ({r.price})" for r in rooms[:5])


def _apply_hitl(pref: UserPreferenceState, mult: dict[str, float], act: HitlAction, analysis: TurnAnalysis, proposed_budget: Optional[float]):
    """Trả (pref mới, mult mới, câu giải thích)."""
    p = pref.model_copy(deep=True)
    m = dict(mult)
    note = ""
    if act is HitlAction.RELAX_BUDGET:
        if analysis.patch.max_price is None:   # người dùng không tự nêu số -> dùng mức đã đề xuất
            new_max = float(proposed_budget) if proposed_budget else round((p.max_price or HITL_TUNING["default_budget"]) * HITL_TUNING["relax_budget_factor"], 0)
            p.max_price = new_max
        m["price"] = HITL_TUNING["relax_price_mult"]
        note = f"đã điều chỉnh ngân sách lên {format_vnd_million(p.max_price if analysis.patch.max_price is None else analysis.patch.max_price)}"
    elif act is HitlAction.DORMITORY:
        p.room_type = RoomType.SLEEPBOX
        p.excluded_room_types = [r for r in p.excluded_room_types if r != RoomType.SLEEPBOX]  # chọn rõ ràng thì thắng
        m["price"] = HITL_TUNING["dormitory_price_mult"]
        note = "chuyển hướng sang tìm kiếm ký túc xá / sleepbox"
    elif act is HitlAction.REDUCE_AMENITIES:
        p.amenities = []
        m["amenity"] = 1.0
        note = "đã lược bớt các yêu cầu tiện ích bắt buộc"
    elif act is HitlAction.BROADEN:
        if p.ward_id is not None:
            p.ward_id = None
        elif p.district_id is not None:
            p.district_id = None
        else:
            p.clear_location()
        m["location"] = 1.0
        note = "mở rộng phạm vi tìm kiếm sang khu vực lân cận"
    return p, m, note


def interpret_turn(
    user_text: str,
    session: Any,
    model: Any,
    *,
    ui_action: Any = None,
    skills: Optional[dict[str, Any]] = None,
) -> TurnPlan:
    pref0: UserPreferenceState = session.preferences
    mult0 = {k: float((session.multipliers or {}).get(k, 1.0)) for k in CRITERIA}
    rooms = list(session.last_rooms or [])
    hitl_pending = bool(session.hitl_streak > 0 or session.proposed_budget is not None)
    has_history = bool(rooms or session.messages or session.hitl_streak > 0)

    action = _as_action(ui_action)
    used_fallback = False
    if action is not None:                      # nút bấm có cấu trúc: không cần LLM
        analysis = TurnAnalysis(intent="hitl_choice", hitl_action=action)
    else:
        recent_user_turns = [text for role, text in (getattr(session, "history", None) or []) if role == "user"][-3:]
        analysis = analyze_turn(
            model, user_text, pref0, rooms_brief=_rooms_brief(rooms), hitl_pending=hitl_pending,
            multipliers=mult0, n_rooms=len(rooms), skills=skills, recent_user_turns=recent_user_turns,
        )
        if analysis is None:
            used_fallback = True
            analysis = legacy_analysis(user_text, has_rooms=bool(rooms), hitl_pending=hitl_pending, has_history=has_history, multipliers=mult0)

    def plan(**kw: Any) -> TurnPlan:
        pref = kw.pop("preferences", pref0)
        mult = kw.pop("multipliers", mult0)
        sem_q = kw.pop("semantic_query", getattr(analysis, "semantic_query", None))
        return TurnPlan(
            analysis=analysis, intent=analysis.intent, preferences=pref, multipliers=mult,
            computed_weights=compute_normalized_weights(pref, mult), used_fallback=used_fallback,
            semantic_query=sem_q, **kw,
        )

    intent = analysis.intent

    # 1) Chặn: injection / off-topic
    if intent in ("prompt_injection", "off_topic"):
        reason = "PROMPT_INJECTION_DETECTED" if intent == "prompt_injection" else "OFF_TOPIC_QUERY"
        return plan(blocked_reason=reason, final_text=SAFE_TEXT[reason])

    # 2) Hỏi tiếp về phòng đã đề xuất
    if intent == "room_followup":
        return plan(is_followup=True, focus_rank=analysis.referenced_room_rank)

    # 3) Tư vấn kỹ năng
    if intent == "skill_advice":
        return plan(matched_skill=analysis.skill_slug)

    # 4) Chào hỏi / mơ hồ -> để clarification_node (LLM) trả lời
    if intent == "smalltalk":
        return plan(needs_clarification=True)

    # 5) Chọn phương án HITL
    explanations: list[str] = []
    pref, mult = pref0, mult0
    commit = True
    reset_hitl = False

    if intent == "hitl_choice":
        act = analysis.hitl_action
        assert act is not None  # _postprocess/legacy bảo đảm
        if act is HitlAction.KEEP:
            return plan(is_keep=True, direct_reply=True, final_text=KEEP_TEXT)
        if act is HitlAction.CUSTOM and (action is not None or analysis.patch.is_empty()):
            return plan(needs_clarification=True, direct_reply=True, final_text=CUSTOM_TEXT)
        pref, mult, note = _apply_hitl(pref0, mult0, act, analysis, session.proposed_budget)
        if note:
            explanations = [note]
        pref = apply_patch(pref, analysis.patch)

    # 6) Tìm mới / chỉnh tiêu chí
    else:
        # Hỗ trợ quay lại tiêu chí trước đó / ban đầu (snapshot rollback)
        history_snapshots = getattr(session, "preference_history", []) or []
        from intelligence.nlu import sanitize_user_text
        from utils.text import strip_accents
        clean_user_text = strip_accents(sanitize_user_text(user_text)).lower()
        is_revert_initial = any(kw in clean_user_text for kw in ("nhu luc dau", "nhu ban dau", "quay lai luc dau", "quay lai ban dau"))
        is_revert_previous = any(kw in clean_user_text for kw in ("nhu luc nay", "quay lai truoc do", "quay lai nhu cu", "nhu cu"))

        base_pref = pref0
        if is_revert_initial and history_snapshots:
            base_pref = history_snapshots[0].model_copy(deep=True)
            explanations.append("đã quay lại tiêu chí ban đầu theo yêu cầu")
            reset_hitl = True
        elif is_revert_previous and history_snapshots:
            target = history_snapshots[-2] if len(history_snapshots) >= 2 else history_snapshots[0]
            base_pref = target.model_copy(deep=True)
            explanations.append("đã quay lại tiêu chí trước đó theo yêu cầu")
            reset_hitl = True

        pref = apply_patch(base_pref, analysis.patch)
        mult = apply_priorities(mult0, analysis.priorities, reset=analysis.reset_priorities)
        explanations.extend([r for r in analysis.priority_reasons if r][:3])

        # Xử lý giảm ngân sách 2 chiều: hỗ trợ cả tăng (nới giá) lẫn giảm (thắt chặt chi tiêu)
        is_asking_cheaper = any(kw in clean_user_text for kw in ("re hon", "re nua", "ha gia", "giam gia", "bot tien", "tiet kiem hon", "thap hon"))
        if is_asking_cheaper:
            if analysis.patch.max_price is None and pref0.max_price:
                new_max = tighten_budget(pref0.max_price)
                if pref.max_price is None or new_max < pref.max_price:
                    pref.max_price = new_max
                    mult["price"] = max(mult.get("price", 1.0), 2.0)
                    explanations.append(f"đã hạ trần ngân sách xuống {format_vnd_million(new_max)} theo yêu cầu rẻ hơn")
            reset_hitl = True
        elif analysis.patch.max_price is not None and pref0.max_price is not None and analysis.patch.max_price < pref0.max_price:
            reset_hitl = True

    vague_info = None
    if analysis.patch.location_is_vague:
        vague_info = {"category": analysis.patch.vague_category, "region": analysis.patch.location_region}

    has_loc = bool(pref.location_text or pref.has_point or pref.district_id or pref.city_id)
    has_budget = bool(pref.max_price or pref.min_price)
    if vague_info:
        needs_clarify = True
    elif has_history or intent == "hitl_choice":
        needs_clarify = False
    else:
        needs_clarify = not has_loc and not has_budget and not pref.amenities

    return plan(
        preferences=pref, multipliers=mult, weight_explanations=explanations,
        needs_clarification=needs_clarify, vague_location_info=vague_info, commit=commit,
        reset_hitl=reset_hitl,
    )


# Wrapper LangGraph nằm ở graph/nodes/understand.py (nhận deps); hàm định tuyến giữ ở đây.


def route_after_understand(state: dict) -> str:
    g = state.get("guardrail_result")
    if g is not None and not g.allowed:
        return "formatter_node"
    if state.get("is_keep_criteria") or state.get("direct_reply"):
        return "formatter_node"
    if state.get("is_followup"):
        return "decision_node"
    if state.get("matched_skill"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"
