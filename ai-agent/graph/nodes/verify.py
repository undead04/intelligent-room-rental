from __future__ import annotations

import logging
from typing import Any

from graph.deps import Deps
from safety.grounding import critic_unsupported_claims, verify_answer_grounding
from intelligence.insights import template_reply


def make_verify_node(deps: Deps):
    def verify_node(state: dict[str, Any]) -> dict[str, Any]:
        final_text = state.get("final_text", "")
        rooms = state.get("retrieved_rooms") or []
        ans_retry = state.get("answer_retry_count", 0)
        retry_notes = list(state.get("retry_notes") or [])
        evidence = state.get("tool_evidence") or []
        update: dict[str, Any] = {}

        # Không có phòng: văn bản do CODE dựng (đề xuất ngân sách, thông báo) nên không có gì để "chống ảo giác"
        if not rooms:
            report = {"is_grounded": True, "groundedness_score": 1.0, "checked": 0, "verified": 0, "context_grounded": state.get("context_grounded", False),
                      "needs_user_consent": state.get("needs_user_consent", False), "proposed_budget": state.get("proposed_budget"),
                      "proposed_budget_str": state.get("proposed_budget_str"), "answer_retries": 0, "retry_notes": [], "issues": [], "fallback_template_used": False}
            return {"answer_grounded": True, "answer_retry_count": ans_retry, "answer_issues": [], "grounding_report": report}

        chk = verify_answer_grounding(final_text, rooms, state.get("preferences"), extra_texts=evidence,
                                      extra_amounts=[a for a in (state.get("proposed_budget"),) if a],
                                      user_text=state.get("user_message", ""))
        issues = list(chk.issues)
        if not issues and deps.enable_critic and deps.verify_answers:     # lớp 2 (LLM) chỉ chạy khi lớp code đã qua
            issues = [f"Phát biểu thiếu căn cứ trong dữ liệu: {c}" for c in critic_unsupported_claims(deps.get_llm("fast"), final_text, rooms, evidence)]

        grounded = not issues
        enforce = deps.verify_answers
        next_retry = ans_retry + (0 if grounded or not enforce else 1)
        fallback_used = False
        if not grounded and enforce:
            retry_notes.append(f"Grounding Retry #{next_retry}: {issues}")
            if next_retry > deps.max_answer_retries:
                if not state.get("is_followup"):
                    update["final_text"] = template_reply(rooms, state.get("insights"))
                fallback_used = True
        answer_grounded = grounded or fallback_used or not enforce      # False => route quay lại decision_node
        update.update({
            "answer_grounded": answer_grounded, "answer_retry_count": next_retry, "retry_notes": retry_notes,
            "answer_issues": [] if answer_grounded else issues,
            "grounding_report": {
                "is_grounded": answer_grounded if enforce else grounded, "groundedness_score": chk.groundedness_score, "checked": chk.checked, "verified": chk.verified,
                "context_grounded": state.get("context_grounded", bool(rooms)), "needs_user_consent": state.get("needs_user_consent", False),
                "proposed_budget": state.get("proposed_budget"), "proposed_budget_str": state.get("proposed_budget_str"),
                "context_retries": state.get("retry_count", 0), "answer_retries": min(next_retry, deps.max_answer_retries),
                "retry_notes": retry_notes, "issues": issues, "fallback_template_used": fallback_used, "enforced": enforce,
            },
        })
        return update

    return verify_node
