from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from domain.schemas import format_vnd_million
from graph.deps import Deps
from graph.tracing import resolve_trace_target, traced_call
from intelligence.nlu import is_daily_quota_exhausted, sanitize_user_text

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Chào bạn! Bạn có thể chia sẻ cụ thể tên địa điểm (trường học, công ty, khu công nghiệp) hoặc khu vực bạn muốn tìm phòng để Homigo hỗ trợ nhé!"
BUDGET_FALLBACK_TEXT = "Bạn muốn nâng hoặc điều chỉnh trần ngân sách lên tối đa khoảng bao nhiêu (ví dụ: 3.5 triệu hay 4 triệu/tháng) ạ?"


class ClarifyReply(BaseModel):
    text: str = Field(description="Câu trả lời/hỏi lại cho người dùng, tự nhiên, lịch sự, ngắn gọn")
    suggestions: list[str] = Field(default_factory=list, description="Gợi ý tên cụ thể (nếu là địa danh chung chung hoặc mốc giá) để người dùng chọn")


def _budget_hint_suggestions(pref: Any) -> list[str]:
    cur_max = getattr(pref, "max_price", None) if pref is not None else None
    if isinstance(cur_max, (int, float)) and cur_max > 0:
        step = 500_000.0
        return [
            format_vnd_million(cur_max + step),
            format_vnd_million(cur_max + step * 2),
        ]
    return ["3.5 triệu", "4 triệu"]


def make_clarification_node(deps: Deps):
    def clarification_node(state: dict[str, Any]) -> dict[str, Any]:
        trace = resolve_trace_target(deps).sink()
        text_in = sanitize_user_text(state.get("user_message", ""))
        vague = state.get("vague_location_info")
        needs_budget = bool(state.get("needs_budget_clarification"))
        pref = state.get("preferences")
        model = deps.get_llm()
        text = ""
        suggestions: list[str] = []
        session = deps.sessions.get_or_create_session(state["session_id"]) if state.get("session_id") else None
        hist = session.compact_history_tuples(window=4) if session and hasattr(session, "compact_history_tuples") else []
        hist_str = ""
        if hist:
            lines = [f"- {'Người dùng' if r == 'user' else 'Trợ lý Homigo'}: {m}" for r, m in hist]
            hist_str = "Lịch sử đối thoại gần nhất (không hỏi lại thông tin người dùng đã trả lời):\n" + "\n".join(lines) + "\n\n"

        budget_suggestions = _budget_hint_suggestions(pref) if needs_budget else []

        if model is not None:
            if needs_budget:
                cur_max = getattr(pref, "max_price", None) if pref is not None else None
                cur_str = format_vnd_million(cur_max) if isinstance(cur_max, (int, float)) and cur_max > 0 else "chưa đặt"
                guide = (
                    f"Người dùng muốn điều chỉnh/nới/giảm ngân sách nhưng CHƯA nêu mức giá mới cụ thể (ngân sách trần hiện tại: {cur_str}). "
                    f"Hãy hỏi lại thật ngắn gọn xem họ muốn đặt trần ngân sách tối đa khoảng bao nhiêu (ví dụ: {', '.join(budget_suggestions)}) "
                    "và đưa các mức giá gợi ý vào `suggestions`."
                )
            elif vague:
                guide = (
                    "Người dùng nhắc tới một địa danh chung chung chưa có tên riêng"
                    f" (nhóm: {vague.get('category')}, khu vực: {vague.get('region') or 'chưa rõ'}). "
                    "Hãy hỏi lại tên cụ thể và đề xuất 3-4 địa điểm nổi tiếng tương ứng tại khu vực đó."
                )
            else:
                guide = (
                    "Nếu người dùng chỉ chào hỏi/cảm ơn thì đáp lại thân thiện rồi mời họ nêu nhu cầu. "
                    "Nếu thiếu khu vực hoặc ngân sách, hãy hỏi khéo léo để bổ sung."
                )
            try:
                call_msgs = [
                    ("system", deps.base_prompt),
                    ("human", f"{guide}\n\n{hist_str}Tiêu chí đã biết:\n{pref.to_context_string() if pref else 'chưa có'}\n\n<user_message>\n{text_in}\n</user_message>"),
                ]
                reply = traced_call(
                    trace,
                    lambda: model.with_structured_output(ClarifyReply).invoke(call_msgs),
                    message_count=len(call_msgs),
                    node="clarification_node",
                    input_data=call_msgs,
                )
                reply = reply if isinstance(reply, ClarifyReply) else ClarifyReply.model_validate(reply)
                text = reply.text.strip()
                suggestions = [s.strip() for s in reply.suggestions if s and s.strip()]
            except Exception as exc:
                err_str = str(exc).lower()
                if is_daily_quota_exhausted(err_str) or any(t in err_str for t in ("429", "rate limit", "resource_exhausted", "quota")):
                    logger.error("clarification_node: LLM chạm rate limit / Quota Exceeded (429).")
                    text = (
                        "⚠️ **Hạn mức sử dụng AI tạm thời bị gián đoạn (Quota Exceeded / 429)**\n\n"
                        "Mô hình AI hiện tại đã đạt giới hạn lượt gọi miễn phí trong ngày của API Key "
                        "(Google Gemini Free Tier Quota Exceeded — 500 requests/ngày).\n\n"
                        "💡 **Cách khắc phục:** Vui lòng cập nhật `OPENAI_API_KEY` mới trong file `ai-agent/.env` để tiếp tục."
                    )
                else:
                    logger.warning("clarification_node: LLM lỗi", exc_info=True)
        if len(text) < 15:
            if needs_budget:
                cur_max = getattr(pref, "max_price", None) if pref is not None else None
                if isinstance(cur_max, (int, float)) and cur_max > 0:
                    text = (
                        f"Ngân sách tối đa hiện tại đang là {format_vnd_million(cur_max)}. "
                        f"Bạn muốn điều chỉnh trần ngân sách lên/xuống tối đa khoảng bao nhiêu (vd: {' hay '.join(budget_suggestions)}) ạ?"
                    )
                else:
                    text = BUDGET_FALLBACK_TEXT
                suggestions = suggestions or budget_suggestions
            else:
                text = FALLBACK_TEXT
        elif needs_budget and not suggestions:
            suggestions = budget_suggestions
        return {"final_text": text, "needs_clarification": True, "retrieved_rooms": [], "follow_up_questions": suggestions}

    return clarification_node
