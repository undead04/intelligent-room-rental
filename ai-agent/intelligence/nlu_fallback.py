"""Đường DỰ PHÒNG khi analyze_turn lỗi (LLM down/timeout/parse lỗi). Keyword, có log để đo tần suất rơi xuống đây.

Giữ hành vi cũ nhưng đã sửa: khớp theo ranh giới từ, bỏ dấu cả hai phía. KHÔNG trích xuất giá/địa danh
(trước đây việc đó cũng cần LLM). Emoji nút bấm chỉ còn được nhận ở đây (frontend cũ); frontend mới gửi `ui_action`.
"""

from __future__ import annotations

import logging
from typing import Optional

from domain.enums import HitlAction
from intelligence.intent_weights import detect_intent_multipliers
from intelligence.nlu import CRITERIA, PreferencePatch, Priorities, TurnAnalysis, mult_to_level
from skills.skills_discovery import match_skill_by_query
from utils.text import contains_phrase, norm_key, tokens

logger = logging.getLogger(__name__)

_EMOJI_ACTION = {
    "👍": HitlAction.RELAX_BUDGET, "🧭": HitlAction.BROADEN, "❌": HitlAction.KEEP,
    "🛌": HitlAction.DORMITORY, "🪄": HitlAction.REDUCE_AMENITIES, "✏": HitlAction.CUSTOM,
}
# thứ tự quan trọng: "không nới" phải được xét trước "nới ngân sách"
_HITL_KEYWORDS: list[tuple[HitlAction, tuple[str, ...]]] = [
    (HitlAction.KEEP, ("giữ nguyên", "không nới", "không đồng ý")),
    (HitlAction.RELAX_BUDGET, ("đồng ý nới", "nới ngân sách", "tăng ngân sách", "nới giá")),
    (HitlAction.BROADEN, ("mở rộng", "bán kính", "lân cận")),
    (HitlAction.DORMITORY, ("ký túc xá", "sleepbox", "ở ghép")),
    (HitlAction.REDUCE_AMENITIES, ("lược bớt",)),
]
_FOLLOWUP_KWS = (
    "top 1", "top 2", "top 3", "phòng 1", "phòng 2", "phòng 3", "căn 1", "căn 2",
    "phòng đầu", "phòng cuối", "so sánh", "chi tiết", "liên hệ", "sdt", "zalo", "số điện thoại",
)
_NOT_FOLLOWUP = ("tìm lại", "tìm thêm", "tìm mới", "phòng khác")
_RANK_WORDS = ("top", "phong", "can")

_VAGUE = {
    "khu công nghiệp": ("khu công nghiệp", "kcn"),
    "trường học": ("trường", "trường học", "trường đại học", "đại học", "trường cấp 3"),
    "bệnh viện": ("bệnh viện", "viện"),
    "chợ/siêu thị": ("chợ", "siêu thị", "tttm", "trung tâm thương mại"),
    "bến xe/nhà ga": ("bến xe", "nhà ga", "ga"),
}
_VAGUE_INDEX = {norm_key(kw): cat for cat, kws in _VAGUE.items() for kw in kws}
_VAGUE_PREFIXES = tuple(norm_key(p) + " " for p in ("tìm phòng gần", "tìm trọ gần", "tìm gần", "phòng gần", "gần", "quanh", "ở", "tại"))
_VAGUE_SEPS = (" o ", " tai ")


def detect_hitl_action(text: str, hitl_pending: bool) -> Optional[HitlAction]:
    s = (text or "").strip()
    if not s:
        return None
    for emoji, action in _EMOJI_ACTION.items():
        if s.startswith(emoji):
            return action
    if norm_key(s) == "tuy chinh tieu chi":
        return HitlAction.CUSTOM
    if not hitl_pending or len(s) > 80:
        return None
    for action, kws in _HITL_KEYWORDS:
        if any(contains_phrase(s, k) for k in kws):
            return action
    return None


def detect_room_followup(text: str, has_rooms: bool) -> tuple[bool, Optional[int]]:
    if not has_rooms or len(text or "") > 160:
        return False, None
    if any(contains_phrase(text, k) for k in _NOT_FOLLOWUP):
        return False, None
    if not any(contains_phrase(text, k) for k in _FOLLOWUP_KWS):
        return False, None
    toks = tokens(text)
    rank = None
    for i, t in enumerate(toks[:-1]):
        if t in _RANK_WORDS and toks[i + 1].isdigit():
            rank = int(toks[i + 1])
            break
    return True, rank


def detect_vague_location(text: str) -> tuple[bool, Optional[str], Optional[str]]:
    """'gần khu công nghiệp ở Bình Dương' -> (True, 'khu công nghiệp', 'binh duong')."""
    clean = f" {norm_key(text)} "
    region = None
    for sep in _VAGUE_SEPS:
        if sep in clean:
            head, region = clean.split(sep, 1)
            clean, region = head, region.strip() or None
            break
    clean = clean.strip()
    for pfx in _VAGUE_PREFIXES:
        if clean.startswith(pfx):
            clean = clean[len(pfx):].strip()
            break
    cat = _VAGUE_INDEX.get(clean)
    return (True, cat, region) if cat else (False, None, None)


def legacy_analysis(
    user_text: str,
    *,
    has_rooms: bool,
    hitl_pending: bool,
    has_history: bool,
    multipliers: Optional[dict[str, float]] = None,
) -> TurnAnalysis:
    logger.warning("NLU fallback (keyword) được dùng cho một lượt")  # đếm dòng log này để biết tần suất LLM lỗi

    action = detect_hitl_action(user_text, hitl_pending)
    if action is not None:
        return TurnAnalysis(intent="hitl_choice", hitl_action=action)

    skill = match_skill_by_query(user_text)
    if skill is not None:
        return TurnAnalysis(intent="skill_advice", skill_slug=skill.slug)

    is_follow, rank = detect_room_followup(user_text, has_rooms)
    if is_follow:
        return TurnAnalysis(intent="room_followup", referenced_room_rank=rank)

    patch = PreferencePatch()
    is_vague, cat, region = detect_vague_location(user_text)
    if is_vague:
        patch = PreferencePatch(location_is_vague=True, vague_category=cat, location_region=region)

    current = multipliers or {k: 1.0 for k in CRITERIA}
    new, reasons = detect_intent_multipliers(user_text, current)
    changed = {k: mult_to_level(new[k]) for k in CRITERIA if new.get(k, 1.0) > current.get(k, 1.0) + 1e-9}
    return TurnAnalysis(
        intent="refine_search" if has_history else "new_search",
        patch=patch,
        priorities=Priorities(**changed),
        priority_reasons=reasons,
    )
