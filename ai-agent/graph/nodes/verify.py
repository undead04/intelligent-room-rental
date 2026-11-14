from __future__ import annotations

from dataclasses import replace
from typing import Any

from graph.deps import Deps
from graph.replies import reply_when_no_rooms
from graph.tracing import emit_verifier_span, resolve_trace_target, traced_call
from intelligence.insights import template_reply
from safety.dod_verifier import (
    _has_fake_success_claim,
    derive_dod_spec,
    verify_dod,
)
from safety.grounding import (
    critic_answer_validation,
    verify_answer_grounding,
)

_NON_RETRYABLE_DOD_CONDS = frozenset({
    "cond_search_trace",
    "cond_skill_trace",
    "cond_max_price",
    "cond_min_price",
    "cond_min_area",
    "cond_max_area",
    "cond_min_bedrooms",
    "cond_max_distance",
    "cond_allowed_room_types",
    "cond_excluded_room_types",
    "cond_amenities",
})


def make_verify_node(deps: Deps):
    def verify_node(state: dict[str, Any]) -> dict[str, Any]:
        final_text = state.get("final_text", "")
        rooms = state.get("retrieved_rooms") or []
        ans_retry = state.get("answer_retry_count", 0)
        retry_notes = list(state.get("retry_notes") or [])
        evidence = list(state.get("tool_evidence") or [])
        pref = state.get("preferences")
        user_msg = state.get("user_message", "")
        intent = state.get("intent", "")
        matched_skill = state.get("matched_skill")
        trace_store = resolve_trace_target(deps)
        frozen_trace = trace_store.frozen_snapshot()
        update: dict[str, Any] = {}

        # Bổ sung ngữ cảnh thị trường/ngân sách khi kiểm tra trường hợp 0 phòng
        extra_texts = list(evidence)
        extra_amounts: list[float] = []
        if state.get("proposed_budget"):
            extra_amounts.append(float(state["proposed_budget"]))
        if state.get("proposed_budget_str"):
            extra_texts.append(str(state["proposed_budget_str"]))
        market = state.get("market_context")
        if market is not None:
            for attr in ("market_min_price_str", "market_avg_price_str", "user_budget_str"):
                val = getattr(market, attr, None)
                if val:
                    extra_texts.append(str(val))

        # 1) Validation 3 tầng theo chi phí tăng dần (Short-circuit tại tầng lỗi đầu tiên)
        chk = verify_answer_grounding(
            final_text,
            rooms,
            pref,
            extra_texts=extra_texts,
            extra_amounts=extra_amounts,
            user_text=user_msg,
            enforce_room_constraints=True,
            short_circuit=True,
        )
        issues = list(chk.issues)
        validation_errors = [err.to_dict() for err in chk.validation_errors]

        # Lớp Critic LLM chỉ chạy khi toàn bộ 3 tầng code validation đã qua
        critic_res = None
        if not issues and deps.enable_critic and deps.verify_answers and rooms:
            fast_llm = deps.get_llm("fast")
            critic_res = traced_call(
                trace_store.sink(),
                lambda: critic_answer_validation(
                    fast_llm, final_text, rooms, extra_texts, user_text=user_msg
                ),
                node="verify_node",
                input_data={"user_text": user_msg, "room_count": len(rooms)},
            )
            for c in critic_res.unsupported_claims:
                msg = f"Phát biểu thiếu căn cứ trong dữ liệu: {c}"
                issues.append(msg)
                validation_errors.append({
                    "tier": "external_cross_check",
                    "field": "answer_text.unsupported_claim",
                    "actual_value": c,
                    "expected": "Chỉ khẳng định chi tiết có căn cứ trong dữ liệu phòng hoặc tool_evidence",
                    "message": msg,
                })
            for q in critic_res.unaddressed_questions:
                msg = f"Chưa trả lời đúng trọng tâm câu hỏi của người dùng: {q}"
                issues.append(msg)
                validation_errors.append({
                    "tier": "external_cross_check",
                    "field": "answer_text.relevance",
                    "actual_value": q,
                    "expected": "Trả lời đúng trọng tâm câu hỏi người dùng",
                    "message": msg,
                })

        # Đồng bộ kết quả Critic (nếu có) trước khi trao cho DoD Verifier độc lập
        grounding_for_dod = chk
        if critic_res is not None and critic_res.unsupported_claims:
            grounding_for_dod = replace(
                chk,
                is_grounded=False,
                groundedness_score=min(chk.groundedness_score, 0.5),
                issues=issues,
            )

        # 2) DoD Verifier độc lập: đọc trạng thái trực tiếp + trace bất biến (không tin tự báo)
        search_args = state.get("last_search_args") or {}
        effective_radius = search_args.get("radius_km") if isinstance(search_args, dict) else None
        spec = derive_dod_spec(
            intent,
            pref,
            user_message=user_msg,
            matched_skill=matched_skill,
            effective_radius_km=effective_radius,
            include_answer_checks=True,
        )
        direct_system_state = {
            "rooms": rooms,
            "tool_evidence": evidence,
            "proposed_budget": state.get("proposed_budget"),
            "admin_not_found": state.get("admin_not_found"),
            "ambiguous_candidates": state.get("ambiguous_candidates"),
            "search_error": state.get("search_error"),
            "lat": getattr(pref, "lat", None) if pref else None,
            "lng": getattr(pref, "lng", None) if pref else None,
        }
        dod_report = verify_dod(
            spec,
            candidate_answer=final_text if isinstance(final_text, str) else "",
            direct_system_state=direct_system_state,
            trace_spans=frozen_trace,
            preferences=pref,
            grounding_result=grounding_for_dod,
            critic_result=critic_res,
            enforce_trace=True,
        )
        verifier_out = dod_report.to_verifier_output()
        overall_passed = (not issues) and dod_report.passed

        all_issues = list(issues)
        for fail in verifier_out.get("failures", []):
            fmsg = fail.get("message")
            if fmsg and fmsg not in all_issues:
                all_issues.append(fmsg)

        enforce = bool(deps.verify_answers)
        failure_cids = {f.get("condition_id") for f in verifier_out.get("failures", [])}
        non_retryable_trace_fail = bool(
            failure_cids & {"cond_search_trace", "cond_skill_trace"}
        ) or bool(state.get("search_error"))
        state_level_only = (
            bool(failure_cids)
            and failure_cids.issubset(_NON_RETRYABLE_DOD_CONDS)
            and all(
                err.get("field", "").startswith("room[")
                for err in validation_errors
            )
            and not (critic_res and (critic_res.unsupported_claims or critic_res.unaddressed_questions))
        )
        # Nếu chỉ lỗi do Tier 1/3/scope text hoặc DoD câu trả lời -> được phép retry decision_node
        has_retryable_text_issue = bool(
            [e for e in validation_errors if not str(e.get("field", "")).startswith("room[")]
        ) or bool(failure_cids - _NON_RETRYABLE_DOD_CONDS)

        next_retry = ans_retry
        fallback_used = False
        next_decision = "pass"
        answer_grounded = True

        if not overall_passed:
            if not enforce:
                next_decision = "bypassed_unforced"
                answer_grounded = True
            elif not has_retryable_text_issue or state_level_only or non_retryable_trace_fail:
                # Lỗi ở tầng hệ thống/ràng buộc phòng hoặc trace: Decision retry không sửa được -> dừng & báo lỗi rõ ràng
                next_decision = "ask_user" if state.get("admin_not_found") or state.get("ambiguous_candidates") else "stop_and_report"
                retry_notes.append(f"Verifier {next_decision}: {all_issues}")
                if not rooms:
                    session = None
                    if deps.sessions is not None and state.get("session_id"):
                        session = deps.sessions.get_or_create_session(state["session_id"])
                    if (
                        non_retryable_trace_fail
                        or _has_fake_success_claim(final_text if isinstance(final_text, str) else "")
                        or not str(final_text).strip()
                    ):
                        update["final_text"] = (
                            reply_when_no_rooms(state, session)
                            if (session is not None and not _has_fake_success_claim(str(final_text)) and not non_retryable_trace_fail)
                            else "Hệ thống chưa truy xuất được dữ liệu phòng thực tế cho yêu cầu này (thiếu xác nhận thực thi công cụ/trạng thái 0 phòng). Bạn vui lòng thử lại hoặc điều chỉnh tiêu chí tìm kiếm."
                        )
                        fallback_used = True
                else:
                    update["final_text"] = (
                        "Hệ thống phát hiện kết quả hiện tại chưa thỏa mãn đầy đủ điều kiện kiểm định DoD "
                        f"({'; '.join(all_issues[:2])}). Bạn vui lòng điều chỉnh lại tiêu chí tìm kiếm hoặc xác nhận yêu cầu để mình lọc lại chính xác hơn."
                    )
                    fallback_used = True
                answer_grounded = True
            else:
                next_retry = ans_retry + 1
                retry_notes.append(f"Grounding Retry #{next_retry}: {all_issues}")
                if next_retry <= deps.max_answer_retries:
                    next_decision = "retry"
                    answer_grounded = False
                else:
                    # Vượt giới hạn tự sửa -> đường thoát xác định, không bao giờ gửi lời báo thành công giả
                    fallback_used = True
                    answer_grounded = True
                    if not rooms:
                        next_decision = "stop_and_report"
                        session = None
                        if deps.sessions is not None and state.get("session_id"):
                            session = deps.sessions.get_or_create_session(state["session_id"])
                        update["final_text"] = (
                            reply_when_no_rooms(state, session)
                            if session is not None and not _has_fake_success_claim(str(final_text))
                            else "Rất tiếc, hiện chưa có dữ liệu phòng phù hợp được xác thực. Vui lòng thử lại với khu vực hoặc ngân sách khác."
                        )
                    elif state.get("is_followup"):
                        from graph.nodes.decision import followup_fallback_reply

                        next_decision = "fallback_template"
                        session = deps.sessions.get_or_create_session(state["session_id"]) if (deps.sessions and state.get("session_id")) else None
                        focus_rank = state.get("focus_rank") or getattr(session, "focused_room_rank", None) or 1
                        target_room = rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else rooms[0]
                        update["final_text"] = followup_fallback_reply(target_room)
                    else:
                        next_decision = "fallback_template"
                        update["final_text"] = template_reply(rooms, state.get("insights"))

        # Ghi kết quả Verifier & quyết định tiếp theo thành một span riêng trong TraceStore
        emit_verifier_span(
            trace_store.sink(),
            verifier_output=verifier_out,
            next_decision=next_decision,
            failed_tier=chk.failed_tier,
            node="verify_node",
            extra={
                "answer_retry": min(next_retry, deps.max_answer_retries),
                "dod_summary": dod_report.summary,
            },
        )

        dod_dict = dod_report.to_dict()
        update.update({
            "answer_grounded": answer_grounded,
            "answer_retry_count": next_retry,
            "retry_notes": retry_notes,
            "answer_issues": [] if answer_grounded else all_issues,
            "dod_report": dod_dict,
            "verifier_result": verifier_out,
            "verifier_decision": next_decision,
            "grounding_report": {
                "is_grounded": answer_grounded if enforce else overall_passed,
                "groundedness_score": chk.groundedness_score,
                "checked": chk.checked,
                "verified": chk.verified,
                "context_grounded": state.get("context_grounded", bool(rooms)),
                "proposed_budget": state.get("proposed_budget"),
                "proposed_budget_str": state.get("proposed_budget_str"),
                "answer_retries": min(next_retry, deps.max_answer_retries),
                "retry_notes": retry_notes,
                "issues": all_issues,
                "fallback_template_used": fallback_used,
                "enforced": enforce,
                "failed_tier": chk.failed_tier,
                "validation_errors": validation_errors,
                "exit_action": next_decision,
                "verifier_output": verifier_out,
                "dod_report": dod_dict,
            },
        })
        return update

    return verify_node
