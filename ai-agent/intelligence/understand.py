"""Node "hiểu lượt chat": điều phối phân tích NLU, cập nhật trạng thái tiêu chí tích lũy, và tính trọng số MCDM.

  interpret_turn(...)         hàm THUẦN: (câu, session, model) -> TurnPlan. Không ghi session.
  compute_normalized_weights  re-export từ intelligence.intent_weights để tính trọng số MCDM.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from domain.enums import Amenity
from domain.schemas import UserPreferenceState
from intelligence.intent_weights import compute_normalized_weights
from intelligence.nlu import (
    CRITERIA,
    LLMQuotaExceededError,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
    sanitize_user_text,
)
from utils.text import norm_key, strip_accents
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
    matched_skill: Optional[str] = None
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


def _build_skill_context(analysis: TurnAnalysis, user_text: str, pref: UserPreferenceState) -> Optional[dict[str, Any]]:
    """Tạo ngữ cảnh riêng cho skill cần tra cứu theo địa danh (không ghi đè session.preferences)."""
    if analysis.skill_slug != "market-price-advisor":
        return None
    loc_text = (analysis.patch.location_text or "").strip() or None
    loc_kind = analysis.patch.location_kind
    loc_region = (analysis.patch.location_region or "").strip() or None
    if not loc_text and pref.location_text:
        clean_q = strip_accents(sanitize_user_text(user_text)).lower()
        if re.search(r"\b(?:o day|o do|khu nay|khu do|khu vuc nay|khu vuc do|quan nay|cho nay|cho do)\b", clean_q):
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


_SEARCH_ORDER_RE = re.compile(
    r"\b(?:tim(?:\s+(?:phong|nha|can|giup|cho|them|moi|o|gan|khu|sang|ben))?|doi\s+sang|chuyen\s+sang|loc|kiem\s+(?:phong|cho)|tim\s+lai|goi\s+y|de\s+xuat)\b",
    re.I,
)
_FOLLOWUP_ORDER_RE = re.compile(
    r"\b(?:(?:phong|can)\s+(?:so|thu|dau(?:\s+tien)?|top|nay|do|kia|vua\s+tim|\d+)\b|top\s*\d+\b|(?:xem|check|coi|kiem\s+tra|hoi)\s+(?:chi\s+tiet|them\s+ve|giup)?\s*(?:phong|can)|dien\s+nuoc|tien\s+coc|chu\s+nha|chu\s+tro)",
    re.I,
)
_ADVISORY_ORDER_RE = re.compile(
    r"\b(?:tu\s+van|hop\s+dong|phap\s+ly|cam\s+nang|kinh\s+nghiem|quyen\s+loi|dat\s+coc|hoan\s+coc|luu\s+y(?:\s+gi|\s+khi)?|gia\s+(?:phong(?:\s+tro)?\s+)?trung\s+binh|mat\s+bang\s+gia|thong\s+ke\s+gia|gia\s+ca)\b",
    re.I,
)


def _plan_multi_intent_order(
    user_text: str,
    intent: str,
    *,
    has_followup: bool,
    has_search: bool,
    has_advisory: bool,
    has_old_rooms: bool,
) -> list[str]:
    """Sắp xếp danh sách tác vụ đa mệnh lệnh theo đúng thứ tự mệnh đề trong câu người dùng."""
    clean = strip_accents(sanitize_user_text(user_text)).lower()
    fallback_base = len(clean) + 10
    m_search = _SEARCH_ORDER_RE.search(clean)
    m_follow = _FOLLOWUP_ORDER_RE.search(clean)
    m_adv = _ADVISORY_ORDER_RE.search(clean)

    pos: dict[str, int] = {}
    if has_search:
        pos["search"] = m_search.start() if m_search else (-1 if intent in ("new_search", "refine_search") else fallback_base + 1)
    if has_followup:
        pos["followup"] = m_follow.start() if m_follow else (-1 if intent == "room_followup" else fallback_base + 2)
    if has_advisory:
        pos["advisory"] = m_adv.start() if m_adv else (-1 if intent == "skill_advice" else fallback_base + 3)

    if "followup" in pos:
        search_before_followup = ("search" in pos) and (pos["search"] < pos["followup"])
        if not has_old_rooms and not search_before_followup:
            pos.pop("followup")

    return [task for task, _ in sorted(pos.items(), key=lambda kv: kv[1])]


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


def _has_unnegated_keyword(text: str, keywords: tuple[str, ...], negation_window: int = 15) -> bool:
    """Kiểm tra từ khóa có xuất hiện trong văn bản mà không bị cụm từ phủ định đi kèm phía trước."""
    negations = ("khong can", "ko can", "dung", "khong phai", "ko phai", "chua can", "khong muon", "ko muon")
    for kw in keywords:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            prefix = text[max(0, idx - negation_window):idx]
            is_negated = any(neg in prefix for neg in negations)
            if not is_negated:
                return True
            start = idx + len(kw)
    return False


def _build_revert_preferences(
    base_pref: UserPreferenceState,
    analysis: TurnAnalysis,
    clean_user_text: str,
    current_pref: UserPreferenceState,
) -> UserPreferenceState:
    """Tái tạo tiêu chí khi người dùng yêu cầu quay lại lượt chat trước hoặc ban đầu."""
    incremental_patch = analysis.patch.model_copy(deep=True)
    incremental_patch.clear = []

    # Nếu người dùng không nhắc đến ngân sách/giá trong lượt rollback thì không ghi đè giá mới
    if not any(kw in clean_user_text for kw in ("trieu", "tr", "cu", "dong", "ngan sach", "gia")):
        incremental_patch.min_price = None
        incremental_patch.max_price = None

    # Giữ lại các tiện ích mới thêm nếu thực sự được người dùng nhắc tới trong câu này (so sánh không dấu)
    kept_amenities = []
    for am in incremental_patch.amenities_add:
        kw_candidates = {am.value.lower(), strip_accents(am.label_vi).lower()}
        if am == Amenity.PET_ALLOWED:
            kw_candidates.update({"pet", "thu cung", "cho", "meo", "boss"})
        if any(w in clean_user_text for w in kw_candidates):
            kept_amenities.append(am)
    incremental_patch.amenities_add = kept_amenities

    pref = apply_patch(base_pref, incremental_patch)

    # Dọn dẹp semantic_query nếu có địa danh của lượt hiện tại không còn nằm trong base
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
    """Khớp lựa chọn của user với 1 ứng viên trong danh sách ambiguous vừa hỏi (theo STT hoặc tên riêng)."""
    if not pending_cands:
        return None

    clean_u = norm_key(sanitize_user_text(user_text))
    # 1. Chọn theo số thứ tự / từ chỉ định vị trí ('1', 'số 2', 'cái đầu')
    m_idx = re.fullmatch(r"(?:chon|lay|so|thu|cai(?:\s+thu)?|phuong\s+an|lua\s+chon)?\s*([1-5])", clean_u)
    if m_idx:
        idx = int(m_idx.group(1)) - 1
        if 0 <= idx < len(pending_cands):
            return pending_cands[idx]
    if re.fullmatch(r"(?:cai|phuong\s+an)?\s*(?:dau|dau\s+tien|thu\s+nhat)", clean_u):
        return pending_cands[0]

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
    skills: Optional[dict[str, Any]] = None,
) -> TurnPlan:
    pref0: UserPreferenceState = session.preferences
    mult0 = {k: float((session.multipliers or {}).get(k, 1.0)) for k in CRITERIA}
    rooms = list(session.last_rooms or [])
    has_history = bool(rooms or session.messages)

    recent_dialog_turns = session.compact_history_tuples(window=4) if hasattr(session, "compact_history_tuples") else None
    recent_user_turns = [text for role, text in (getattr(session, "history", None) or []) if role == "user"][-3:]
    try:
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

    # 1.5) Lập kế hoạch thực thi tuần tự cho Đa Mệnh Lệnh (Plan & Execute):
    # Sắp xếp tự do theo đúng thứ tự mệnh đề user yêu cầu (hỗ trợ mọi hoán vị followup / search / advisory).
    multi_tasks: list[str] = []
    multi_has_followup = False
    multi_has_search = False
    multi_has_advisory = False
    if getattr(analysis, "is_multi_intent", False):
        followup_requested = (analysis.referenced_room_rank is not None or intent == "room_followup")
        multi_has_advisory = bool(analysis.skill_slug)
        multi_has_search = (not analysis.patch.is_empty()) or (
            intent in ("new_search", "refine_search") and not followup_requested and not multi_has_advisory
        )
        multi_tasks = _plan_multi_intent_order(
            user_text,
            intent,
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
                matched_skill=analysis.skill_slug if multi_has_advisory else None,
                skill_context=_build_skill_context(analysis, user_text, pref0) if multi_has_advisory else None,
                is_followup=(multi_tasks[0] == "followup"),
                focus_rank=focus_rank if multi_has_followup else None,
                current_task=multi_tasks[0],
                pending_tasks=multi_tasks[1:],
            )

    # 2) Hỏi tiếp về phòng đã đề xuất
    if intent == "room_followup" and not multi_tasks:
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
    if intent == "skill_advice" and not multi_tasks:
        return plan(matched_skill=analysis.skill_slug, skill_context=_build_skill_context(analysis, user_text, pref0))

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
        pref = _build_revert_preferences(base_pref, analysis, clean_user_text, pref0)
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
        pref = _build_revert_preferences(base_pref, analysis, clean_user_text, pref0)
        mult = {k: 1.0 for k in CRITERIA}
        explanations.append("đã quay lại tiêu chí ban đầu theo yêu cầu")
    elif is_revert_previous and history_snapshots:
        target = history_snapshots[-2] if len(history_snapshots) >= 2 else history_snapshots[0]
        base_pref = target.model_copy(deep=True)
        pref = _build_revert_preferences(base_pref, analysis, clean_user_text, pref0)
        explanations.append("đã quay lại tiêu chí trước đó theo yêu cầu")
    else:
        pref = apply_patch(base_pref, analysis.patch)
        mult = apply_priorities(mult0, analysis.priorities, reset=analysis.reset_priorities)

        # Kết hợp lại với địa danh đang hỏi dở (ambiguous) nếu lượt này user chọn 1 ứng viên hoặc trả lời ngắn quận/tỉnh/cơ sở
        pending_loc = getattr(session, "pending_ambiguous_location", None)
        pending_cands = list(getattr(session, "pending_ambiguous_candidates", []) or [])
        is_pivot = bool(
            re.search(r"\b(?:thoi|doi\s+sang|khong\s+tim|tim\s+cho\s+khac|khu\s+khac|chuyen\s+sang|bo\s+qua)\b", clean_user_text)
        )
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
                    or bool(re.match(r"^(?:cơ\s*sở|cs|khu\s*vực|phía|bên|quận|q\.?\s*\d|huyện|phường|p\.?\s*\d|tp\.?|tỉnh)\b", new_loc, re.I))
                )
                if looks_modifier and not _PLACE_HINTS.search(new_loc):
                    if re.match(r"^(?:cơ\s*sở|cs)\b", new_loc, re.I):
                        combined = f"{pending_loc} {new_loc}"
                    else:
                        combined = f"{pending_loc}, {new_loc}"
                    pref.set_location(combined, kind="place")
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
    has_budget = bool(pref.max_price or pref.min_price)
    if is_vague_loc:
        needs_clarify = True
    elif has_history:
        needs_clarify = False
    else:
        needs_clarify = not has_loc and not has_budget and not pref.amenities

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
            vague_location_info=vague_info,
            matched_skill=analysis.skill_slug if multi_has_advisory else None,
            skill_context=_build_skill_context(analysis, user_text, pref) if multi_has_advisory else None,
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
        vague_location_info=vague_info,
        commit=commit,
    )


__all__ = [
    "SAFE_TEXT",
    "TurnPlan",
    "compute_normalized_weights",
    "interpret_turn",
]
