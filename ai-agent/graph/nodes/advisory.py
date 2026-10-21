from __future__ import annotations

import logging
from typing import Any

from graph.deps import Deps
from graph.tracing import traced_call, tool_event
from intelligence.nlu import sanitize_user_text
from prompts.advisory_prompt import build_advisory_prompt

logger = logging.getLogger(__name__)

SORRY = "Xin lỗi bạn, Homigo chưa tra cứu được cẩm nang tư vấn này lúc này. Bạn thử hỏi lại sau ít phút, hoặc cho Homigo biết nhu cầu tìm phòng của bạn nhé!"
MAX_GUIDE_CHARS = 6000
MAX_REF_CHARS = 3000


def _msg_text(res: Any) -> str:
    c = getattr(res, "content", res)
    return c if isinstance(c, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in (c or []))


def make_advisory_node(deps: Deps):
    def advisory_node(state: dict[str, Any]) -> dict[str, Any]:
        slug = state.get("matched_skill") or ""
        query = sanitize_user_text(state.get("user_message", ""))
        trace = list(state.get("trace_events") or [])
        out = {"retrieved_rooms": [], "needs_clarification": False, "trace_events": trace}

        try:
            res = tool_event(trace, "consult_housing_skill", {"skill_name": slug}, lambda: deps.consult_skill(slug, query),
                             lambda r: {"ok": bool(r.get("ok"))})
        except Exception:
            res = {}
        guide = str(res.get("instructions") or "") if res.get("ok") else ""
        refs = "\n\n".join(str(v) for v in (res.get("references") or {}).values())[:MAX_REF_CHARS]
        model = deps.get_llm("main")
        if not guide or model is None:
            return {**out, "final_text": SORRY}
        skill = deps.skills().get(slug)
        label = getattr(skill, "name", slug) or slug
        system = build_advisory_prompt(slug, guide[:MAX_GUIDE_CHARS], references=refs, base_prompt=deps.base_prompt)
        try:
            reply = traced_call(trace, lambda: model.invoke([("system", system), ("human", f"<user_message>\n{query}\n</user_message>")]))
            text = _msg_text(reply).strip()
        except Exception:
            logger.warning("advisory_node: LLM lỗi", exc_info=True)
            text = ""
        if len(text) < 30:
            text = SORRY
        elif slug not in text and label not in text:
            text = f"💡 **Homigo AI - Tư vấn chuyên sâu ({label}):**\n\n{text}"
        return {**out, "final_text": text}

    return advisory_node
