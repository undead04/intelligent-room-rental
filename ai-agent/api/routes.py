"""Các FastAPI endpoints (/chat, /chat/stream, /health) và HousingAgentService."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid
from typing import Any, Iterator, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.sse import stream_graph_events
from core.config import DEFAULT_PAGE_SIZE, MAX_PAGINATION_PAGES, get_runtime_settings
from core.paths import DEFAULT_DB_PATH
from core.session_store import PersistentSessionStore
from domain.schemas import AgentResponse, SessionRoomsPageResponse
from graph import build_housing_graph, default_deps, run_turn
from tools.http import set_client

logger = logging.getLogger(__name__)

SESSION_STORE = PersistentSessionStore(DEFAULT_DB_PATH)
DEPS = default_deps(sessions=SESSION_STORE)
HOUSING_GRAPH = build_housing_graph(DEPS)


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        max_length=4000,
        description="Nội dung câu hỏi hoặc yêu cầu tìm kiếm phòng của người dùng",
    )
    conversation_history: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Lịch sử chat các lượt trước",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Mã phiên làm việc để tích lũy tiêu chí đa lượt",
    )


def prepare_session_with_history(
    session_id: Optional[str],
    conversation_history: Optional[list[dict[str, Any]]],
) -> tuple[str, Any]:
    """Khởi tạo hoặc đồng bộ lịch sử hội thoại từ Client vào SessionStore an toàn."""
    effective_sid = (session_id or uuid.uuid4().hex).strip()
    if conversation_history is not None and len(conversation_history) == 0:
        SESSION_STORE.clear_session(effective_sid)

    session = SESSION_STORE.get_or_create_session(effective_sid)

    if conversation_history and len(session.history) == 0:
        with session.lock:
            if len(session.history) == 0:
                restored = []
                for m in conversation_history[-20:]:
                    role = m.get("role")
                    content = str(m.get("content") or "").strip()
                    if not content:
                        continue
                    if role in ("user", "assistant"):
                        restored.append((role, content))
                session.history = restored

    return effective_sid, session


class HousingAgentService:
    """Service chính điều phối AI Agent, vận hành 100% trên nền LangGraph State Machine."""

    def __init__(self, settings: Any = None):
        self.settings = settings

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Thực thi trực tiếp qua LangGraph State Machine."""
        effective_session_id, _ = prepare_session_with_history(session_id, conversation_history)
        return run_turn(
            HOUSING_GRAPH,
            user_message,
            session_id=effective_session_id,
        )

    def run_stream(
        self,
        user_message: str,
        conversation_history: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Generator phát SSE thời gian thực qua LangGraph State Machine."""
        effective_session_id, _ = prepare_session_with_history(session_id, conversation_history)
        return stream_graph_events(
            user_message=user_message,
            effective_session_id=effective_session_id,
            graph=HOUSING_GRAPH,
        )


service = HousingAgentService()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Đóng HTTP Connection Pool sạch sẽ khi tắt server."""
    yield
    try:
        set_client(None)
    except Exception:
        pass


app = FastAPI(
    title="Homigo Smart Housing AI Agent API",
    description="Microservice cung cấp API tư vấn và hỗ trợ ra quyết định tìm phòng trọ thông minh",
    version="2.3.0",
    lifespan=_lifespan,
)

allowed_origins = list(get_runtime_settings().cors_allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "Homigo AI Agent", "version": "2.3.0"}


@app.delete("/api/v1/session/{session_id}")
@app.delete("/session/{session_id}")
def delete_session_endpoint(session_id: str) -> dict[str, str]:
    """Xóa bộ nhớ session trên server để reset hội thoại hoàn toàn."""
    SESSION_STORE.clear_session(session_id.strip())
    return {"status": "ok", "session_id": session_id, "message": "Đã xoá phiên làm việc thành công."}


@app.get("/api/v1/session/{session_id}/rooms", response_model=SessionRoomsPageResponse)
@app.get("/session/{session_id}/rooms", response_model=SessionRoomsPageResponse)
def get_session_rooms_page(
    session_id: str,
    page: int = Query(1, ge=1, le=MAX_PAGINATION_PAGES, description="Số trang muốn xem (1..10)"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=20, description="Số phòng mỗi trang"),
) -> SessionRoomsPageResponse:
    """Phân trang tức thì danh sách phòng đã lưu trong phiên (0 LLM, 0 Embedding)."""
    clean_sid = session_id.strip()
    if not clean_sid:
        raise HTTPException(status_code=400, detail="session_id không được để trống.")
    session = SESSION_STORE.get_or_create_session(clean_sid)
    rooms, eff_page, eff_size, total_rooms, total_pages = SESSION_STORE.switch_page(session, page, page_size)
    return SessionRoomsPageResponse(
        session_id=clean_sid,
        rooms=rooms,
        page=eff_page,
        page_size=eff_size,
        total_rooms=total_rooms,
        total_pages=total_pages,
    )


@app.post("/api/v1/chat", response_model=AgentResponse)
@app.post("/chat", response_model=AgentResponse)
def chat_endpoint(request: ChatRequest) -> AgentResponse:
    try:
        return service.run(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception(f"Lỗi khi xử lý hội thoại AI: {e}")
        raise HTTPException(status_code=500, detail="Lỗi máy chủ khi xử lý yêu cầu tìm phòng.")


@app.post("/api/v1/chat/stream")
@app.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        service.run_stream(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
