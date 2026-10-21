from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from graph.deps import Deps
from graph.tracing import traced_call
from intelligence.nlu import sanitize_user_text

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Chào bạn! Bạn có thể chia sẻ cụ thể tên địa điểm (trường học, công ty, khu công nghiệp) hoặc khu vực bạn muốn tìm phòng để Homigo hỗ trợ nhé!"


class ClarifyReply(BaseModel):
    text: str = Field(description="Câu trả lời/hỏi lại cho người dùng, tự nhiên, lịch sự, ngắn gọn")
    suggestions: list[str] = Field(default_factory=list, description="Gợi ý tên cụ thể (nếu là địa danh chung chung) để người dùng chọn")


def make_clarification_node(deps: Deps):
    def clarification_node(state: dict[str, Any]) -> dict[str, Any]:
        trace = list(state.get("trace_events") or [])
        text_in = sanitize_user_text(state.get("user_message", ""))
        vague = state.get("vague_location_info")
        pref = state.get("preferences")
        model = deps.get_llm("fast") or deps.get_llm("main")
        text = ""
        suggestions: list[str] = []
        if model is not None:
            guide = ("Người dùng nhắc tới một địa danh chung chung chưa có tên riêng"
                     f" (nhóm: {vague.get('category')}, khu vực: {vague.get('region') or 'chưa rõ'}). Hãy hỏi lại tên cụ thể và đề xuất 3-4 địa điểm nổi tiếng tương ứng tại khu vực đó."
                     if vague else
                     "Nếu người dùng chỉ chào hỏi/cảm ơn thì đáp lại thân thiện rồi mời họ nêu nhu cầu. Nếu thiếu khu vực hoặc ngân sách, hãy hỏi khéo léo để bổ sung.")
            try:
                reply = traced_call(trace, lambda: model.with_structured_output(ClarifyReply).invoke([
                    ("system", deps.base_prompt),
                    ("human", f"{guide}\n\nTiêu chí đã biết:\n{pref.to_context_string() if pref else 'chưa có'}\n\n<user_message>\n{text_in}\n</user_message>"),
                ]))
                reply = reply if isinstance(reply, ClarifyReply) else ClarifyReply.model_validate(reply)
                text = reply.text.strip()
                suggestions = [s.strip() for s in reply.suggestions if s and s.strip()]
            except Exception:
                logger.warning("clarification_node: LLM lỗi", exc_info=True)
        if len(text) < 15:
            text = FALLBACK_TEXT
        return {"final_text": text, "needs_clarification": True, "retrieved_rooms": [], "follow_up_questions": suggestions, "trace_events": trace}

    return clarification_node
