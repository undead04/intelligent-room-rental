"""HousingAgentService: FastAPI Microservice interface cho AI Agent,
ủy quyền toàn bộ quy trình thực thi sang LangGraph State Machine (housing_graph) 8 nodes
kết hợp trích xuất danh sách phòng và bảng phân tích hỗ trợ ra quyết định.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph import build_decision_insights, housing_graph
from guardrails import check_guardrails
from memory import memory_manager
from schemas import AgentResponse, DecisionInsight, RoomItem, UserPreferenceState

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., description="Nội dung câu hỏi hoặc yêu cầu tìm kiếm phòng của người dùng")
    conversation_history: Optional[list[dict]] = Field(default=None, description="Lịch sử chat các lượt trước")
    session_id: Optional[str] = Field(default=None, description="Mã phiên làm việc để tích lũy tiêu chí đa lượt")
    use_graph: Optional[bool] = Field(default=True, description="Sử dụng LangGraph State Machine (housing_graph) 8-node")


class HousingAgentService:
    """Service chính cung cấp API interface cho AI Agent, vận hành 100% trên nền LangGraph State Machine."""

    def __init__(self, settings: Any = None):
        self.session_histories: dict[str, list] = {}

    _build_decision_insights = staticmethod(build_decision_insights)

    def run_graph(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Thực thi qua LangGraph State Machine (housing_graph) 8 nodes."""
        effective_session_id = session_id or uuid.uuid4().hex
        if conversation_history is not None and len(conversation_history) == 0:
            memory_manager.clear_session(effective_session_id)

        state = {
            "user_message": user_message,
            "session_id": effective_session_id,
        }
        result = housing_graph.invoke(state)
        resp = result.get("final_response")
        if isinstance(resp, AgentResponse):
            return resp
        return AgentResponse(
            session_id=effective_session_id,
            text_reply=result.get("final_text", ""),
            rooms=result.get("retrieved_rooms", []),
            insights=result.get("insights"),
        )

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Alias thống nhất về run_graph (hoàn toàn tương thích ngược)."""
        return self.run_graph(
            user_message=user_message,
            conversation_history=conversation_history,
            session_id=session_id,
        )

    def run_stream(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
        use_graph: bool = True,
    ):
        """Generator phát SSE thời gian thực qua LangGraph Stream:
        - event: trace (báo trạng thái từng node trong LangGraph pipeline)
        - event: text_delta (câu trả lời sinh từ AI)
        - event: done (toàn bộ AgentResponse hoàn chỉnh kèm danh sách phòng & insights)
        """
        effective_session_id = session_id or uuid.uuid4().hex

        # 1. Kiểm tra guardrails an toàn
        guard = check_guardrails(user_message)
        if not guard.allowed:
            safe_reply = guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI."
            yield f"event: text_delta\ndata: {json.dumps({'delta': safe_reply}, ensure_ascii=False)}\n\n"
            blocked_resp = AgentResponse(
                session_id=effective_session_id,
                text_reply=safe_reply,
                rooms=[],
                insights=None,
                current_preferences=UserPreferenceState(),
                need_clarification=False,
                follow_up_questions=["Khu vực Thủ Đức / Làng Đại học", "Ngân sách dưới 3.5 triệu/tháng"],
                grounding_report={"is_grounded": True, "blocked_by_guardrail": True, "reason": guard.reason},
                hitl_proposal=None,
                trace_events=[],
            )
            yield f"event: done\ndata: {blocked_resp.model_dump_json()}\n\n"
            return

        if conversation_history is not None and len(conversation_history) == 0:
            memory_manager.clear_session(effective_session_id)

        state = {
            "user_message": user_message,
            "session_id": effective_session_id,
        }
        step = 0
        final_resp: Optional[AgentResponse] = None
        try:
            for node_name, node_update in housing_graph.stream(state, stream_mode="updates"):
                step += 1
                trace_ev = {
                    "type": "tool_finished",
                    "step": step,
                    "tool_name": node_name,
                    "status": "ok",
                }
                yield f"event: trace\ndata: {json.dumps(trace_ev, ensure_ascii=False)}\n\n"
                if isinstance(node_update, dict) and "final_response" in node_update:
                    final_resp = node_update["final_response"]

            if not final_resp:
                final_resp = self.run_graph(user_message, conversation_history, effective_session_id)

            if final_resp and final_resp.text_reply:
                yield f"event: text_delta\ndata: {json.dumps({'delta': final_resp.text_reply}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {final_resp.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception(f"Lỗi khi stream LangGraph: {e}")
            final_resp = self.run_graph(user_message, conversation_history, effective_session_id)
            yield f"event: done\ndata: {final_resp.model_dump_json()}\n\n"


# Khởi tạo singleton service dùng chung
service = HousingAgentService()

# Khởi tạo ứng dụng FastAPI phục vụ Frontend Next.js
app = FastAPI(
    title="Homigo Smart Housing AI Agent API",
    description="Microservice cung cấp API tư vấn và hỗ trợ ra quyết định tìm phòng trọ thông minh",
    version="1.0.0",
)

# Cấu hình CORS cho phép Next.js Frontend truy vấn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
@app.get("/health")
def health_check() -> dict[str, str]:
    """Kiểm tra tình trạng hoạt động của AI Agent service."""
    return {"status": "ok", "service": "Homigo AI Agent", "version": "1.0.0"}


@app.post("/api/v1/chat", response_model=AgentResponse)
@app.post("/chat", response_model=AgentResponse)
def chat_endpoint(request: ChatRequest) -> AgentResponse:
    """Endpoint chính nhận tin nhắn từ giao diện người dùng và trả về phản hồi kèm danh sách phòng & insight."""
    try:
        return service.run_graph(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception(f"Lỗi khi xử lý hội thoại AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chat/stream")
@app.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """Endpoint SSE stream từng bước thực thi và stream từng token câu trả lời thời gian thực."""
    return StreamingResponse(
        service.run_stream(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
            use_graph=True,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("service:app", host="0.0.0.0", port=8001, reload=True)
