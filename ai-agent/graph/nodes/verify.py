from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.config import LLM_NLU_TEMPERATURE
from graph.deps import Deps
from graph.nodes.decision import followup_fallback_reply
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
    "cond_market_stats_trace",
    "cond_no_unrequested_search",
    "cond_no_premature_detail_on_search",
    "cond_no_duplicate_detail_call",
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
        pending_tasks = list(state.get("pending_tasks") or [])
        cur_task = state.get("current_task")
        is_multi_step = bool(pending_tasks or state.get("partial_replies"))
        is_advisory_step = (cur_task == "advisory") or (
            not cur_task
            and intent == "skill_advice"
            and bool(matched_skill or state.get("matched_skills"))
        )
        if is_advisory_step:
            eff_skill = matched_skill
            eff_skills = state.get("matched_skills")
            eff_intent = "skill_advice"
            eff_user_msg = "" if (is_multi_step or state.get("needs_clarification")) else user_msg
            grounding_rooms = []
            grounding_pref = None
            enforce_constraints = False
            dod_pref = None
        else:
            eff_skill = None if ("advisory" in pending_tasks or cur_task in ("followup", "search")) else matched_skill
            eff_skills = None if eff_skill is None else state.get("matched_skills")
            grounding_rooms = rooms
            grounding_pref = pref
            enforce_constraints = True
            dod_pref = pref
            if cur_task == "followup":
                eff_intent = "room_followup"
                eff_user_msg = "" if is_multi_step else user_msg
            elif cur_task == "search":
                eff_intent = "new_search" if intent in ("skill_advice", "room_followup") else intent
                eff_user_msg = (state.get("semantic_query") or "") if is_multi_step else user_msg
            else:
                eff_intent = intent
                eff_user_msg = user_msg

        # Bổ sung ngữ cảnh thị trường/ngân sách khi kiểm tra trường hợp 0 phòng
        extra_texts = list(evidence)
        extra_amounts: list[float] = []
        market = state.get("market_context")
        if market is not None:
            for attr in ("market_min_price", "market_avg_price"):
                amount = getattr(market, attr, None)
                if amount:
                    extra_amounts.append(float(amount))
            for attr in ("market_min_price_str", "market_avg_price_str", "user_budget_str"):
                val = getattr(market, attr, None)
                if val:
                    extra_texts.append(str(val))

        # 1) Validation 3 tầng theo chi phí tăng dần (Short-circuit tại tầng lỗi đầu tiên)
        chk = verify_answer_grounding(
            final_text,
            grounding_rooms,
            grounding_pref,
            extra_texts=extra_texts,
            extra_amounts=extra_amounts,
            user_text=user_msg,
            enforce_room_constraints=enforce_constraints,
            short_circuit=True,
        )
        issues = list(chk.issues)
        validation_errors = [err.to_dict() for err in chk.validation_errors]

        # Lớp Critic LLM chỉ chạy khi toàn bộ 3 tầng code validation đã qua
        critic_res = None
        if not issues and deps.enable_critic and deps.verify_answers and grounding_rooms:
            critic_llm = deps.get_llm(temperature=LLM_NLU_TEMPERATURE)
            critic_res = traced_call(
                trace_store.sink(),
                lambda: critic_answer_validation(
                    critic_llm, final_text, grounding_rooms, extra_texts, user_text=eff_user_msg
                ),
                node="verify_node",
                input_data={"user_text": eff_user_msg, "room_count": len(grounding_rooms)},
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
        effective_radius = (
            (search_args.get("max_distance_km") or search_args.get("radius_km"))
            if isinstance(search_args, dict)
            else None
        )
        is_advisory_sorry = isinstance(final_text, str) and final_text.startswith(
            "Xin lỗi bạn, Homigo chưa tra cứu được cẩm nang"
        )
        require_market_stats = (
            is_advisory_step
            and not bool(state.get("needs_clarification"))
            and not is_advisory_sorry
        )
        allow_unrequested_search = (
            intent in ("skill_advice", "page_navigation")
            and cur_task != "search"
            and "search" not in pending_tasks
        )
        forbid_premature_detail = (cur_task == "search" and "followup" in pending_tasks)
        forbid_dup_detail = (cur_task == "followup" or bool(state.get("is_followup")))
        reused_cached = set(state.get("reused_cached_skills") or [])
        dod_intent = eff_intent
        dod_skill = eff_skill
        dod_skills = eff_skills
        if is_advisory_step and reused_cached:
            raw_eff = list(eff_skills or ([eff_skill] if eff_skill else []))
            uncached_skills = [s for s in raw_eff if s not in reused_cached]
            if not uncached_skills:
                dod_skill = None
                dod_skills = []
                if dod_intent == "skill_advice":
                    dod_intent = "skill_advice_cached"
            else:
                dod_skill = uncached_skills[0]
                dod_skills = uncached_skills
        spec = derive_dod_spec(
            dod_intent,
            dod_pref,
            user_message=eff_user_msg,
            matched_skill=dod_skill,
            matched_skills=dod_skills,
            effective_radius_km=effective_radius,
            include_answer_checks=not is_advisory_sorry,
            require_market_stats_trace=require_market_stats,
            allow_unrequested_search_check=allow_unrequested_search,
            forbid_detail_on_search_step=forbid_premature_detail,
            forbid_duplicate_detail_call=forbid_dup_detail,
        )
        direct_system_state = {
            "rooms": grounding_rooms,
            "tool_evidence": evidence,
            "market_context": state.get("market_context"),
            "admin_not_found": state.get("admin_not_found"),
            "location_not_found": state.get("location_not_found"),
            "ambiguous_candidates": state.get("ambiguous_candidates"),
            "search_error": state.get("search_error"),
            "lat": getattr(dod_pref, "lat", None) if dod_pref else None,
            "lng": getattr(dod_pref, "lng", None) if dod_pref else None,
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
            failure_cids
            & {
                "cond_search_trace",
                "cond_skill_trace",
                "cond_market_stats_trace",
                "cond_no_unrequested_search",
                "cond_no_premature_detail_on_search",
                "cond_no_duplicate_detail_call",
            }
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
                next_decision = "ask_user" if state.get("admin_not_found") or state.get("location_not_found") or state.get("ambiguous_candidates") else "stop_and_report"
                retry_notes.append(f"Verifier {next_decision}: {all_issues}")
                if is_advisory_step:
                    if non_retryable_trace_fail or not str(final_text).strip():
                        update["final_text"] = (
                            "Hệ thống chưa xác thực được đầy đủ dữ liệu tư vấn hoặc thống kê giá thực tế cho yêu cầu này. "
                            "Bạn vui lòng thử lại hoặc nêu rõ tên quận/huyện cần tra cứu nhé."
                        )
                        if "cond_no_unrequested_search" in failure_cids:
                            update["retrieved_rooms"] = []
                            update["searched"] = False
                        fallback_used = True
                elif not rooms:
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
                    if "cond_no_unrequested_search" in failure_cids:
                        update["retrieved_rooms"] = []
                        update["searched"] = False
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
                    if is_advisory_step:
                        next_decision = "stop_and_report"
                        update["final_text"] = (
                            "Rất tiếc, hiện hệ thống chưa thể xác thực đầy đủ thông tin tư vấn cho câu hỏi này. "
                            "Bạn vui lòng thử hỏi lại cụ thể hơn nhé."
                        )
                    elif not rooms:
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
                        next_decision = "fallback_template"
                        session = deps.sessions.get_or_create_session(state["session_id"]) if (deps.sessions and state.get("session_id")) else None
                        focus_rank = state.get("focus_rank") or getattr(session, "focused_room_rank", None) or 1
                        target_room = next(
                            (r for r in rooms if getattr(r, "rank", None) == focus_rank),
                            rooms[focus_rank - 1] if 1 <= focus_rank <= len(rooms) else rooms[0],
                        )
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
        if answer_grounded and pending_tasks:
            step_reply = str(update.get("final_text", final_text) or "").strip()
            partials = list(state.get("partial_replies") or [])
            if step_reply:
                partials.append(step_reply)
            next_task = pending_tasks[0]
            rest_tasks = pending_tasks[1:]
            # Khi chạy search -> followup mà search ra 0 phòng: bỏ qua followup để tránh lặp lỗi 0 phòng
            if next_task == "followup" and not rooms:
                next_task = rest_tasks[0] if rest_tasks else None
                rest_tasks = rest_tasks[1:] if rest_tasks else []
            if next_task is None:
                update.update({
                    "partial_replies": partials,
                    "current_task": None,
                    "pending_tasks": [],
                    "is_followup": False,
                    "final_text": "",
                })
            else:
                update.update({
                    "partial_replies": partials,
                    "current_task": next_task,
                    "pending_tasks": rest_tasks,
                    "is_followup": (next_task == "followup"),
                    "answer_retry_count": 0,
                    "answer_issues": [],
                    "answer_grounded": True,
                })
                if next_task == "search":
                    update.update({
                        "retrieved_rooms": [],
                        "insights": None,
                        "final_text": "",
                        "tool_evidence": [],
                    })
                elif next_task == "followup":
                    update.update({
                        "final_text": "",
                        "tool_evidence": [],
                    })
        elif answer_grounded:
            update.update({
                "current_task": None,
                "pending_tasks": [],
                "is_followup": False,
            })
        return update

    return verify_node
