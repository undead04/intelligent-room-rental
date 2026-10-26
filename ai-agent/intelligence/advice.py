"""Sinh câu tư vấn CÓ RÀNG BUỘC: LLM chỉ viết phần văn bản định tính; CODE điền mọi số liệu (giá, địa chỉ, diện tích, điểm, chênh lệch giá).

=> Ảo giác về giá/mã phòng/diện tích trở nên bất khả thi về cấu trúc; verify_answer_grounding còn lại vai trò lưới an toàn thứ hai
(vẫn quét phần văn bản LLM để bắt con số lọt vào).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field

from domain.schemas import RoomItem, UserPreferenceState
from intelligence.insights import DEFAULT_CHECKLIST, price_trade_off, room_lines
from intelligence.payload_builder import build_decision_user_message
from prompts.decision_prompt import ADVICE_RULES

logger = logging.getLogger(__name__)

MAX_FIELD_CHARS = 500


class Advice(BaseModel):
    intro: str = Field(description="1-2 câu mở đầu thân thiện (không chứa con số/mã phòng)")
    top_reason: str = Field(description="Lý do phòng Top 1 phù hợp nhất dựa trên explain_match (không chứa con số)")
    comparison: str = Field(description="So sánh định tính Top 1 với Top 2 về vị trí, tiện nghi, an ninh; để trống nếu chỉ có 1 phòng")
    checklist: list[str] = Field(default_factory=list, description="1-3 điểm cần kiểm tra thực tế khi đi xem phòng")


def _clean(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    keep = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s in ("---", "***", "___") or (s.startswith("|") and s.endswith("|")):
            continue
        keep.append(s)
    out = " ".join(keep)
    return out if len(out) <= limit else out[:limit].rstrip() + "…"


def render_advice(advice: Advice, rooms: Sequence[RoomItem], max_rooms: int = 5) -> str:
    if not rooms:
        lines = [_clean(advice.intro) or "Homigo hiện chưa tìm thấy phòng trọ nào phù hợp."]
        if _clean(advice.top_reason):
            lines.extend(["", f"💡 **Nhận định:** {_clean(advice.top_reason)}"])
        if _clean(advice.comparison):
            lines.extend(["", f"⚖️ **Gợi ý mở rộng:** {_clean(advice.comparison)}"])
        checklist = [c for c in (_clean(c, 200) for c in advice.checklist) if c][:3] or DEFAULT_CHECKLIST
        lines.extend(["", "📋 **Lưu ý khi đi xem phòng:**", *[f"- {c}" for c in checklist]])
        return "\n".join(lines)

    top1 = rooms[0]
    lines = [_clean(advice.intro) or f"Homigo đã tìm được {len(rooms)} phòng phù hợp với nhu cầu của bạn:", ""]
    for r in rooms[:max_rooms]:
        lines.extend(room_lines(r))
    lines.extend(["", f"🏆 **Lựa chọn tối ưu nhất: {top1.title}**"])
    if _clean(advice.top_reason):
        lines.append(f"- {_clean(advice.top_reason)}")
    if len(rooms) > 1:
        cmp_line = " ".join(x for x in (price_trade_off(rooms[0], rooms[1]), _clean(advice.comparison)) if x)
        if cmp_line:
            lines.extend(["", f"⚖️ **So với Top 2:** {cmp_line}"])
    checklist = [c for c in (_clean(c, 200) for c in advice.checklist) if c][:3] or DEFAULT_CHECKLIST
    lines.extend(["", "📋 **Lưu ý khi đi xem phòng:**", *[f"- {c}" for c in checklist]])
    return "\n".join(lines)


def generate_advice(
    model: Any,
    system_prompt: str,
    question: str,
    pref: UserPreferenceState,
    rooms: Sequence[RoomItem],
    *,
    retry_issues: Optional[Sequence[str]] = None,
    focus_rank: Optional[int] = None,
) -> Optional[Advice]:
    """None khi không có model hoặc lỗi (caller dùng template_reply)."""
    if model is None or not rooms:
        return None
    try:
        sys = system_prompt if "QUY TẮC BẮT BUỘC" in system_prompt or "TUYỆT ĐỐI KHÔNG" in system_prompt else f"{system_prompt}\n\n{ADVICE_RULES}"
        raw = model.with_structured_output(Advice).invoke([
            ("system", sys),
            ("human", build_decision_user_message(question, pref, rooms, retry_issues=retry_issues, focus_rank=focus_rank)),
        ])
        return raw if isinstance(raw, Advice) else Advice.model_validate(raw)
    except Exception:
        logger.warning("generate_advice lỗi -> dùng đường dự phòng", exc_info=True)
        return None


class ZeroResultAdvice(BaseModel):
    analysis: str = Field(description="1-2 câu phân tích khách quan vì sao chưa tìm thấy phòng dựa trên tương quan giữa yêu cầu người dùng (ngân sách, tiện ích, vị trí) và thực tế thị trường")
    market_assessment: str = Field(description="Nhận định mặt bằng giá tại khu vực (kèm số liệu giá sàn, giá trung bình nếu có). Nếu người dùng đặt giá quá cao hoặc quá thấp so với khu vực, hãy giải thích rõ")
    suggestions: list[str] = Field(description="2-3 hướng giải pháp cụ thể (nâng/hạ ngân sách, gợi ý các khu vực lân cận cụ thể, gợi ý mô hình phòng hoặc lược bớt tiện ích)")
    closing_question: str = Field(description="Câu hỏi mở thân thiện để người dùng tự do nhắn lại quyết định tiếp theo")


def render_zero_result_advice(advice: ZeroResultAdvice, location: str = "") -> str:
    loc_part = f" tại **{location}**" if location else ""
    lines = [
        f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với các điều kiện lọc của bạn{loc_part}.\n",
        f"📊 **Nhận định từ Cố vấn Homigo:**\n- {advice.analysis.strip()}",
    ]
    if advice.market_assessment and advice.market_assessment.strip():
        lines.append(f"- {advice.market_assessment.strip()}")
    lines.append("\n💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**")
    for i, s in enumerate(advice.suggestions, 1):
        lines.append(f"  {i}. {s.strip()}")
    if advice.closing_question and advice.closing_question.strip():
        lines.append(f"\n👉 {advice.closing_question.strip()}")
    return "\n".join(lines)
