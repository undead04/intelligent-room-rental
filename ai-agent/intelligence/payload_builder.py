"""Đóng gói dữ liệu cho LLM tư vấn: khung <rooms_data> chống injection gián tiếp, số liệu tính sẵn, phản hồi khi retry.

Thiết kế tối ưu KV-Cache / Prompt Caching:
- Toàn bộ ngữ cảnh bán tĩnh (<criteria>, <rooms_data>, <prefetched_listing_detail>) luôn đặt ở ĐẦU message (Prefix).
- Phần biến đổi động theo từng lượt/retry (<user_message>, <focus>, <previous_attempt_issues>) luôn đặt ở CUỐI message (Suffix).
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from domain.schemas import RoomItem, UserPreferenceState

_SKIP_HINTS = ("image", "img", "photo", "thumb", "avatar", "url", "link", "phone", "contact")
_SKIP_KEYS = {"latPercent", "lngPercent", "lat", "lng", "rankText"}


def _shrink(v: Any) -> Any:
    if isinstance(v, str):
        return v if len(v) <= 240 else v[:240] + "…"
    if isinstance(v, list):
        return [_shrink(x) for x in v[:12]]
    if isinstance(v, dict):
        return {k: _shrink(x) for k, x in list(v.items())[:20]}
    return v


def compact_room(r: RoomItem) -> dict[str, Any]:
    """Bản gọn của phòng cho LLM: bỏ ảnh/toạ độ/liên hệ; giữ area_m2, match_percent, room_type, inferred_tags."""
    d = r.model_dump(mode="json", exclude_none=True)
    return {k: _shrink(v) for k, v in d.items() if k not in _SKIP_KEYS and not any(h in k.lower() for h in _SKIP_HINTS)}


def format_retry_feedback(issues: Sequence[str]) -> str:
    return (
        "<previous_attempt_issues>\nLần trả lời trước có các lỗi sau, hãy viết lại và sửa đúng các lỗi này:\n- "
        + "\n- ".join(issues)
        + "\n</previous_attempt_issues>"
    )


def build_decision_context_message(
    pref: UserPreferenceState,
    rooms: Sequence[RoomItem],
    *,
    target_room_detail: Optional[str] = None,
) -> str:
    """Tạo khối ngữ cảnh dữ liệu phòng & tiêu chí cố định (Prefix) nhằm tối ưu KV-Cache / Prompt Caching."""
    parts = [
        f"<criteria>\n{pref.to_context_string()}\n</criteria>",
        f"<rooms_data>\n{json.dumps([compact_room(r) for r in rooms], ensure_ascii=False)}\n</rooms_data>",
    ]
    if target_room_detail:
        parts.append(f"<prefetched_listing_detail>\n{target_room_detail}\n</prefetched_listing_detail>")
    return "\n".join(parts)


def build_decision_query_message(
    question: str,
    *,
    focus_rank: Optional[int] = None,
    retry_issues: Optional[Sequence[str]] = None,
) -> str:
    """Tạo message chứa câu hỏi người dùng và feedback retry (phần đuôi động, đặt sau Context Prefix)."""
    q = (question or "").replace("</user_message>", "").replace("<user_message>", "")
    parts = [f"<user_message>\n{q}\n</user_message>"]
    if focus_rank:
        parts.append(f"<focus>Người dùng đang hỏi về phòng Top {focus_rank}.</focus>")
    if retry_issues:
        parts.append(format_retry_feedback(retry_issues))
    return "\n".join(parts)


def build_decision_user_message(
    question: str,
    pref: UserPreferenceState,
    rooms: Sequence[RoomItem],
    *,
    retry_issues: Optional[Sequence[str]] = None,
    focus_rank: Optional[int] = None,
    target_room_detail: Optional[str] = None,
) -> str:
    """Ghép Context Prefix cố định trước, Query Suffix động sau để kích hoạt KV-Cache khi retry hoặc hỏi tiếp."""
    prefix = build_decision_context_message(pref, rooms, target_room_detail=target_room_detail)
    suffix = build_decision_query_message(question, focus_rank=focus_rank, retry_issues=retry_issues)
    return f"{prefix}\n{suffix}"
