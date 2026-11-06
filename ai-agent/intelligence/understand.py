"""Node "hiểu lượt chat": điều phối phân tích NLU, cập nhật trạng thái tiêu chí tích lũy, và tính trọng số MCDM.

  interpret_turn(...)       hàm THUẦN: (câu, session, model) -> TurnPlan. Không ghi session.
  understand_turn_node(...) wrapper LangGraph: là NƠI DUY NHẤT ghi session.preferences / session.multipliers.
  route_after_understand    định tuyến sau bước hiểu nhu cầu.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from domain.schemas import UserPreferenceState, format_vnd_million
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import (
    CRITERIA,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
    sanitize_user_text,
)
from utils.text import strip_accents

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
    matched_skill: Optional[str] = None
    is_followup: bool = False
    direct_reply: bool = False          # có final_text sẵn, bỏ qua LLM trả lời -> đi thẳng formatter
    focus_rank: Optional[int] = None
    final_text: Optional[str] = None
    blocked_reason: Optional[str] = None
    vague_location_info: Optional[dict[str, Any]] = None
    commit: bool = False                # True => wrapper ghi preferences/multipliers vào session
    semantic_query: Optional[str] = None


def _rooms_brief(rooms: list) -> str:
    return "; ".join(f"Top {r.rank}: {r.title} ({r.price})" for r in rooms[:5])


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


def interpret_turn(
    user_text: str,
    session: Any,
    model: Any,
    *,
    skills: Optional[dict[str, Any]] = None,
) -> TurnPlan:
    pref0: UserPreferenceState = session.preferences
    mult0 = {k: float((session.multipliers or {}).get(k, 1.0)) for k in CRITERIA}
    rooms = list(session.last_rooms or [])
    has_history = bool(rooms or session.messages)

    recent_dialog_turns = session.compact_history_tuples(window=4) if hasattr(session, "compact_history_tuples") else None
    recent_user_turns = [text for role, text in (getattr(session, "history", None) or []) if role == "user"][-3:]
    analysis = analyze_turn(
        model,
        user_text,
        pref0,
        rooms_brief=_rooms_brief(rooms),
        multipliers=mult0,
        n_rooms=len(rooms),
        skills=skills,
        recent_dialog_turns=recent_dialog_turns,
        recent_user_turns=recent_user_turns,
    )

    if analysis is not None and getattr(analysis.patch, "location_is_vague", False):
        loc_str = strip_accents(str(analysis.patch.location_text or user_text)).lower()
        specific_landmarks = (
            "dhqg", "lang dai hoc", "spkt", "hcmute", "bach khoa", "ueh", "hutech",
            "quan 1", "quan 7", "quan 10", "q1", "q7", "q10", "ben thanh", "phu my hung",
        )
        if any(kw in loc_str for kw in specific_landmarks):
            analysis.patch.location_is_vague = False

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

    # 1.5) Chặn mềm Đa Mệnh Lệnh (Multi-Intent Soft Guardrail): lưu sẵn tiêu chí và phản hồi tự nhiên
    if getattr(analysis, "is_multi_intent", False):
        has_patch = not analysis.patch.is_empty()
        pref = apply_patch(pref0, analysis.patch) if has_patch else pref0
        mult = apply_priorities(mult0, analysis.priorities, reset=analysis.reset_priorities) if has_patch else mult0
        explanations = [r for r in analysis.priority_reasons if r][:3] if has_patch else []
        reply_text = _build_multi_intent_reply(analysis, skills, has_patch)
        return plan(
            preferences=pref,
            multipliers=mult,
            weight_explanations=explanations,
            direct_reply=True,
            needs_clarification=True,
            final_text=reply_text,
            commit=has_patch,
        )

    # 2) Hỏi tiếp về phòng đã đề xuất
    if intent == "room_followup":
        if not rooms:
            # Chưa có phòng nào được đề xuất trong phiên -> chuyển sang hỏi làm rõ nhu cầu
            return plan(needs_clarification=True)
        current_focus = (
            analysis.referenced_room_rank
            if analysis.referenced_room_rank is not None
            else getattr(session, "focused_room_rank", None)
        )
        return plan(is_followup=True, focus_rank=current_focus or 1)

    # 3) Tư vấn kỹ năng
    if intent == "skill_advice":
        return plan(matched_skill=analysis.skill_slug)

    # 4) Chào hỏi / mơ hồ -> để clarification_node trả lời
    if intent == "smalltalk":
        return plan(needs_clarification=True)

    # 5) Tìm mới / chỉnh tiêu chí
    explanations: list[str] = []
    pref, mult = pref0, mult0
    commit = True

    history_snapshots = getattr(session, "preference_history", []) or []
    clean_user_text = strip_accents(sanitize_user_text(user_text)).lower()

    turn_match = re.search(r"\b(?:luot|buoc|lan)\s*(?:chat\s*)?(?:thu\s*)?(\d+)\b", clean_user_text)
    is_revert_explicit_turn = False
    target_turn_num: Optional[int] = None
    if turn_match and any(kw in clean_user_text for kw in ("quay lai", "tro ve", "nhu", "y chang", "giong", "tim lai")):
        target_turn_num = int(turn_match.group(1))
        is_revert_explicit_turn = True

    is_revert_initial = (target_turn_num == 1) or any(
        kw in clean_user_text for kw in ("nhu luc dau", "nhu ban dau", "quay lai luc dau", "quay lai ban dau")
    )
    is_revert_previous = any(
        kw in clean_user_text for kw in ("nhu luc nay", "quay lai truoc do", "quay lai nhu cu", "nhu cu")
    )

    base_pref = pref0
    turn_snaps = getattr(session, "turn_snapshots", []) or []
    if is_revert_explicit_turn and target_turn_num and 1 <= target_turn_num <= len(turn_snaps):
        base_pref = turn_snaps[target_turn_num - 1].model_copy(deep=True)
        incremental_patch = analysis.patch.model_copy(deep=True)
        incremental_patch.clear = []
        if not any(kw in clean_user_text for kw in ("trieu", "tr", "cu", "dong", "ngan sach", "gia")):
            incremental_patch.min_price = None
            incremental_patch.max_price = None
        incremental_patch.amenities_add = [
            am for am in incremental_patch.amenities_add
            if any(w in clean_user_text for w in (am.value, am.label_vi.lower(), "pet", "thú cưng", "thu cung"))
        ]
        pref = apply_patch(base_pref, incremental_patch)
        if analysis.semantic_query and pref0.location_text:
            if pref0.location_text.lower() in analysis.semantic_query.lower() and pref0.location_text.lower() not in (base_pref.location_text or "").lower():
                analysis.semantic_query = None
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
        incremental_patch = analysis.patch.model_copy(deep=True)
        incremental_patch.clear = []
        if not any(kw in clean_user_text for kw in ("trieu", "tr", "cu", "dong", "ngan sach", "gia")):
            incremental_patch.min_price = None
            incremental_patch.max_price = None
        incremental_patch.amenities_add = [
            am for am in incremental_patch.amenities_add
            if any(w in clean_user_text for w in (am.value, am.label_vi.lower(), "pet", "thú cưng", "thu cung"))
        ]
        pref = apply_patch(base_pref, incremental_patch)
        if analysis.semantic_query and pref0.location_text:
            if pref0.location_text.lower() in analysis.semantic_query.lower() and pref0.location_text.lower() not in (base_pref.location_text or "").lower():
                analysis.semantic_query = None
        mult = {k: 1.0 for k in CRITERIA}
        explanations.append("đã quay lại tiêu chí ban đầu theo yêu cầu")
    elif is_revert_previous and history_snapshots:
        target = history_snapshots[-2] if len(history_snapshots) >= 2 else history_snapshots[0]
        base_pref = target.model_copy(deep=True)
        incremental_patch = analysis.patch.model_copy(deep=True)
        incremental_patch.clear = []
        if not any(kw in clean_user_text for kw in ("trieu", "tr", "cu", "dong", "ngan sach", "gia")):
            incremental_patch.min_price = None
            incremental_patch.max_price = None
        incremental_patch.amenities_add = [
            am for am in incremental_patch.amenities_add
            if any(w in clean_user_text for w in (am.value, am.label_vi.lower(), "pet", "thú cưng", "thu cung"))
        ]
        pref = apply_patch(base_pref, incremental_patch)
        if analysis.semantic_query and pref0.location_text:
            if pref0.location_text.lower() in analysis.semantic_query.lower() and pref0.location_text.lower() not in (base_pref.location_text or "").lower():
                analysis.semantic_query = None
        explanations.append("đã quay lại tiêu chí trước đó theo yêu cầu")
    else:
        pref = apply_patch(base_pref, analysis.patch)
        mult = apply_priorities(mult0, analysis.priorities, reset=analysis.reset_priorities)
    explanations.extend([r for r in analysis.priority_reasons if r][:3])

    # Xử lý ưu tiên giá rẻ ("rẻ hơn", "hạ giá") khi người dùng không nêu con số cụ thể
    is_asking_cheaper = any(kw in clean_user_text for kw in ("re hon", "re nua", "ha gia", "giam gia", "bot tien", "tiet kiem hon", "thap hon"))
    if is_asking_cheaper and analysis.patch.max_price is None:
        if pref.max_price and pref.max_price > 0:
            reduced = round((pref.max_price * 0.85) / 50_000.0) * 50_000.0
            if reduced < pref.max_price:
                pref.max_price = float(reduced)
                explanations.append(f"giảm trần ngân sách xuống {format_vnd_million(pref.max_price)} theo yêu cầu rẻ hơn")
        mult["price"] = max(mult.get("price", 1.0), 2.0)
        explanations.append("ưu tiên tìm các phòng có giá rẻ nhất")

    # Xử lý nới ngân sách ("đắt hơn", "mắc hơn", "nới giá", "tăng ngân sách", "cao hơn", "phòng xịn hơn") khi người dùng không nêu con số cụ thể
    is_asking_higher = any(kw in clean_user_text for kw in ("dat hon", "mac hon", "noi gia", "tang ngan sach", "tang gia", "cao hon", "phong xin hon", "phong dep hon", "phong cao cap hon"))
    if is_asking_higher and analysis.patch.max_price is None:
        if pref.max_price and pref.max_price > 0:
            increased = round((pref.max_price * 1.15) / 50_000.0) * 50_000.0
            if increased > pref.max_price:
                pref.max_price = float(increased)
                explanations.append(f"nới trần ngân sách lên {format_vnd_million(pref.max_price)} để tìm thêm phòng tiện nghi hơn")
        mult["amenity"] = max(mult.get("amenity", 1.0), 1.8)

    vague_info = None
    if analysis.patch.location_is_vague:
        vague_info = {"category": analysis.patch.vague_category, "region": analysis.patch.location_region}
    elif analysis.patch.location_region:
        vague_info = {"category": None, "region": analysis.patch.location_region}

    has_loc = bool(pref.location_text or pref.has_point or pref.district_id or pref.city_id)
    has_budget = bool(pref.max_price or pref.min_price)
    if analysis.patch.location_is_vague:
        needs_clarify = True
    elif has_history:
        needs_clarify = False
    else:
        needs_clarify = not has_loc and not has_budget and not pref.amenities

    return plan(
        preferences=pref,
        multipliers=mult,
        weight_explanations=explanations,
        needs_clarification=needs_clarify,
        vague_location_info=vague_info,
        commit=commit,
    )


def route_after_understand(state: dict) -> str:
    g = state.get("guardrail_result")
    if g is not None and not g.allowed:
        return "formatter_node"
    if state.get("direct_reply"):
        return "formatter_node"
    if state.get("is_followup"):
        return "decision_node"
    if state.get("matched_skill"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"
