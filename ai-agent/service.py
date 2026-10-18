"""HousingAgentService: Service chính cung cấp API interface cho AI Agent,
vận hành trên nền tảng LangGraph State Machine kết hợp Intent-Aware Dynamic MCDM,
Memory & Preference State Management và Guardrails Security.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from graph import build_decision_insights, housing_graph
from memory import memory_manager
from schemas import AgentResponse, DecisionInsight, RoomItem, TradeOffAnalysis

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., description="Nội dung câu hỏi hoặc yêu cầu tìm kiếm phòng của người dùng")
    conversation_history: Optional[list[dict]] = Field(default=None, description="Lịch sử chat các lượt trước")
    session_id: Optional[str] = Field(default=None, description="Mã phiên làm việc để tích lũy tiêu chí đa lượt")


class HousingAgentService:
    def __init__(self, settings: Any = None):
        self.settings = settings
        self.graph = housing_graph

    def _extract_rooms_from_messages(self, messages: list[BaseMessage]) -> list[RoomItem]:
        """Trích xuất danh sách phòng từ ToolMessage của tool search_rooms."""
        rooms: list[RoomItem] = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == "search_rooms":
                try:
                    payload = json.loads(msg.content)
                    if isinstance(payload, dict) and payload.get("ok"):
                        raw_items = payload.get("data", [])
                        if isinstance(raw_items, list):
                            for idx, raw_item in enumerate(raw_items, 1):
                                rooms.append(RoomItem.from_backend_result(raw_item, rank=idx))
                            break
                except Exception as e:
                    logger.warning(f"Lỗi parse dữ liệu từ search_rooms: {e}")
        return rooms

    def _build_decision_insights(self, rooms: list[RoomItem]) -> Optional[DecisionInsight]:
        """Tổng hợp DecisionInsight dựa trên explain_match của Top 1 và các phòng so sánh."""
        return build_decision_insights(rooms)

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Thực thi một lượt hội thoại qua LangGraph State Machine."""
        session = memory_manager.get_or_create_session(session_id)

        # Đồng bộ conversation_history nếu client truyền vào
        if conversation_history and not session.messages:
            for turn in conversation_history:
                role = turn.get("role") or turn.get("sender")
                content = turn.get("content") or turn.get("text", "")
                if role in ("user", "human"):
                    session.messages.append(HumanMessage(content=content))
                elif role in ("ai", "assistant"):
                    session.messages.append(AIMessage(content=content))

        # Chuẩn bị initial state cho LangGraph
        initial_state = {
            "session_id": session.session_id,
            "user_message": user_message,
            "preferences": session.preferences,
            "messages": session.messages + [HumanMessage(content=user_message)],
        }

        # Thực thi đồ thị trạng thái
        final_state = self.graph.invoke(initial_state)
        response = final_state.get("final_response")
        if response:
            if not response.session_id:
                response.session_id = session.session_id
            return response

        # Fallback nếu final_response chưa được gán
        return AgentResponse(
            session_id=session.session_id,
            text_reply=final_state.get("final_text", ""),
            rooms=final_state.get("retrieved_rooms", []),
            insights=final_state.get("insights"),
            current_preferences=final_state.get("preferences", session.preferences),
            need_clarification=final_state.get("needs_clarification", False),
        )


# Khởi tạo singleton service
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
        return service.run(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception(f"Lỗi khi xử lý hội thoại AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("service:app", host="0.0.0.0", port=8001, reload=True)
