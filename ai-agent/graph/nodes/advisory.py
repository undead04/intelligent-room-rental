from __future__ import annotations

import logging
from typing import Any

from graph.deps import Deps
from graph.tracing import resolve_trace_target, traced_call, tool_event
from intelligence.nlu import sanitize_user_text
from prompts.advisory_prompt import build_advisory_prompt
from utils.text import extract_message_text

logger = logging.getLogger(__name__)

SORRY = "Xin lỗi bạn, Homigo chưa tra cứu được cẩm nang tư vấn này lúc này. Bạn thử hỏi lại sau ít phút, hoặc cho Homigo biết nhu cầu tìm phòng của bạn nhé!"
MAX_GUIDE_CHARS = 6000
MAX_REF_CHARS = 3000


def make_advisory_node(deps: Deps):
    def advisory_node(state: dict[str, Any]) -> dict[str, Any]:
        slug = state.get("matched_skill") or ""
        query = sanitize_user_text(state.get("user_message", ""))
        trace = resolve_trace_target(deps).sink()
        out = {"retrieved_rooms": [], "needs_clarification": False}

        try:
            res = tool_event(
                trace,
                "consult_housing_skill",
                {"skill_name": slug, "query": query},
                lambda: deps.consult_skill(slug, query),
                lambda r: {"ok": bool(r.get("ok"))},
                node="advisory_node",
            )
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
        session = deps.sessions.get_or_create_session(state["session_id"]) if state.get("session_id") else None
        hist = (
            session.compact_history_as_messages(window=4)
            if session is not None and hasattr(session, "compact_history_as_messages")
            else (session.history_as_messages(window=4) if session is not None and hasattr(session, "history_as_messages") else [])
        )
        msgs: list[tuple[str, str]] = [("system", system)]
        for m in hist:
            role = "human" if getattr(m, "type", "") == "human" else "ai"
            msgs.append((role, extract_message_text(m)))
        msgs.append(("human", f"<user_message>\n{query}\n</user_message>"))
        try:
            reply = traced_call(
                trace,
                lambda: model.invoke(msgs),
                message_count=len(msgs),
                node="advisory_node",
                input_data=msgs,
            )
            text = extract_message_text(reply).strip()
        except Exception:
            logger.warning("advisory_node: LLM lỗi", exc_info=True)
            text = ""
        if len(text) < 30:
            text = SORRY
        elif slug not in text and label not in text:
            text = f"💡 **Homigo AI - Tư vấn chuyên sâu ({label}):**\n\n{text}"
        return {**out, "final_text": text}

    return advisory_node
