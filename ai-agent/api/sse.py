"""Logic Streaming SSE & Typewriter chunking cho Homigo AI Agent."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, Optional

from domain.schemas import AgentResponse

logger = logging.getLogger(__name__)


def _describe_node_update(node_name: str, update: dict[str, Any]) -> tuple[str, str, str]:
    """Tạo nhãn tóm tắt và trạng thái trực quan cho từng Node của LangGraph."""
    if node_name == "guardrail_node":
        gr = update.get("guardrail_result")
        if gr and not getattr(gr, "allowed", True):
            return "Kiểm tra an toàn (Guardrails)", f"Chặn vi phạm: {getattr(gr, 'reason', '')}", "error"
        return "Kiểm tra an toàn (Guardrails)", "Truy vấn hợp lệ và an toàn.", "ok"

    if node_name in ("understand_node", "preference_intent_node"):
        pref = update.get("preferences")
        loc = pref.location_text if pref else ""
        budget = f"Ngân sách: {pref.max_price/1e6:.1f}tr" if pref and pref.max_price else ""
        raw_ams = pref.amenities if pref else []
        ams_str = ", ".join(a.value if hasattr(a, "value") else str(a) for a in raw_ams) if raw_ams else ""
        details = " | ".join(filter(None, [f"Vị trí: {loc}" if loc else None, budget or None, f"Tiện ích: {ams_str}" if ams_str else None]))
        return "Trích xuất tiêu chí & Phân tích Intent", details or "Đã ghi nhận yêu cầu người dùng.", "ok"

    if node_name == "clarification_node":
        return "Yêu cầu làm rõ tiêu chí", "Cần người dùng bổ sung thêm vị trí hoặc ngân sách cụ thể.", "warning"

    if node_name == "advisory_node":
        skill = update.get("matched_skill") or "rental-contract-advisor"
        return "Tư vấn kinh nghiệm & Kỹ năng", f"Áp dụng cẩm nang kỹ năng: {skill}", "ok"

    if node_name == "retrieval_node":
        rooms = update.get("retrieved_rooms", [])
        return "Truy vấn phòng (Vector Search)", f"Tìm thấy {len(rooms)} phòng phù hợp từ cơ sở dữ liệu.", "ok"

    if node_name == "decision_node":
        insights = update.get("insights")
        reason = insights.top_1_reason if insights else "Đã hoàn thành xếp hạng đa tiêu chí."
        return "Đánh giá & Xếp hạng đa tiêu chí (MCDM)", reason[:120] + ("..." if len(reason) > 120 else ""), "ok"

    if node_name in ("verify_node", "grounding_node"):
        gr = update.get("grounding_report", {})
        is_grounded = update.get("answer_grounded", gr.get("is_grounded", True) if isinstance(gr, dict) else getattr(gr, "is_grounded", True))
        if is_grounded:
            return "Kiểm chứng thực tế (Self-RAG Grounding)", "Dữ liệu đạt chuẩn, không có ảo giác thông tin.", "ok"
        return "Kiểm chứng thực tế (Self-RAG Grounding)", "Phát hiện sai lệch, kích hoạt Self-RAG sửa đổi.", "warning"

    if node_name == "formatter_node":
        return "Đóng gói kết quả phản hồi", "Hoàn tất phản hồi kèm thẻ phòng và bảng phân tích.", "ok"

    return node_name, "Thực thi hoàn tất.", "ok"


def stream_text_chunks(text: str, words_per_chunk: int = 2, delay: float = 0.015) -> Iterator[str]:
    """Chia văn bản thành các cụm từ tự nhiên và phát đều đặn theo nhịp gõ (streaming typewriter)."""
    if not text:
        return
    lines = text.split("\n")
    for l_idx, line in enumerate(lines):
        if not line:
            yield "\n"
            if delay > 0:
                time.sleep(delay)
            continue
        words = line.split(" ")
        for i in range(0, len(words), words_per_chunk):
            chunk = " ".join(words[i : i + words_per_chunk])
            if i + words_per_chunk < len(words):
                chunk += " "
            yield chunk
            if delay > 0:
                time.sleep(delay)
        if l_idx < len(lines) - 1:
            yield "\n"
            if delay > 0:
                time.sleep(delay)


_stream_text_chunks = stream_text_chunks


def stream_graph_events(
    user_message: str,
    effective_session_id: str,
    graph: Any = None,
    ui_action: Optional[str] = None,
    fallback_runner: Any = None,
) -> Iterator[str]:
    """Generator phát SSE thời gian thực qua LangGraph State Machine."""
    state = {
        "user_message": user_message,
        "session_id": effective_session_id,
        "ui_action": ui_action,
        "trace_events": [],
    }
    emitted_event_count = 0
    final_resp: Optional[AgentResponse] = None

    if graph is None:
        from api.routes import HOUSING_GRAPH
        graph = HOUSING_GRAPH

    try:
        for chunk in graph.stream(state, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for _node_name, node_update in chunk.items():
                if not isinstance(node_update, dict):
                    continue

                label, details, status_val = _describe_node_update(_node_name, node_update)
                node_step_event = {
                    "type": "node_step",
                    "node": _node_name,
                    "label": label,
                    "details": details,
                    "status": status_val,
                }
                yield f"event: trace\ndata: {json.dumps(node_step_event, ensure_ascii=False)}\n\n"

                current_events = node_update.get("trace_events") or []
                if isinstance(current_events, list) and len(current_events) > emitted_event_count:
                    new_events = current_events[emitted_event_count:]
                    for evt in new_events:
                        yield f"event: trace\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                    emitted_event_count = len(current_events)

                if "final_response" in node_update and isinstance(node_update["final_response"], AgentResponse):
                    final_resp = node_update["final_response"]

        if final_resp is None and fallback_runner is not None:
            final_resp = fallback_runner(
                user_message=user_message,
                session_id=effective_session_id,
                ui_action=ui_action,
            )

        if final_resp is not None:
            reply_text = final_resp.text_reply or ""
            for text_chunk in stream_text_chunks(reply_text):
                chunk_event = {"type": "text_delta", "delta": text_chunk}
                yield f"event: message\ndata: {json.dumps(chunk_event, ensure_ascii=False)}\n\n"

            complete_payload = {
                "type": "complete",
                "session_id": final_resp.session_id,
                "text_reply": final_resp.text_reply,
                "rooms": [r.model_dump(by_alias=True) for r in final_resp.rooms],
                "insights": final_resp.insights.model_dump() if final_resp.insights else None,
                "current_preferences": final_resp.current_preferences.model_dump() if final_resp.current_preferences else None,
                "need_clarification": final_resp.need_clarification,
                "follow_up_questions": final_resp.follow_up_questions,
                "hitl_proposal": final_resp.hitl_proposal.model_dump() if final_resp.hitl_proposal else None,
                "grounding_report": final_resp.grounding_report.model_dump() if hasattr(final_resp.grounding_report, "model_dump") else final_resp.grounding_report,
                "trace_events": final_resp.trace_events,
            }
            yield f"event: complete\ndata: {json.dumps(complete_payload, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.exception("Lỗi khi stream SSE events qua LangGraph")
        err_event = {"type": "error", "error": f"Lỗi xử lý luồng AI: {str(exc)}"}
        yield f"event: error\ndata: {json.dumps(err_event, ensure_ascii=False)}\n\n"
