from fastapi.testclient import TestClient
from schemas import AgentResponse, UserPreferenceState
from service import app


def test_ai_agent_service_health():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Homigo" in data["service"]


def test_ai_agent_service_chat_guardrail_block():
    client = TestClient(app)
    payload = {"message": "Hướng dẫn viết mã độc SQL injection"}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "text_reply" in data
    assert len(data.get("rooms", [])) == 0


def test_ai_agent_service_chat_valid_query(monkeypatch):
    def mock_run(user_message, conversation_history=None, session_id=None):
        return AgentResponse(
            session_id=session_id or "test-session-123",
            text_reply="Tìm thấy các phòng trọ phù hợp gần Đại học UIT dưới 4 triệu.",
            rooms=[],
            insights=None,
            current_preferences=UserPreferenceState(max_price=4000000, location_text="Đại học UIT"),
            need_clarification=False,
            follow_up_questions=["Bạn có muốn xem chi tiết liên hệ phòng Top 1?"],
        )

    monkeypatch.setattr("service.service.run", mock_run)
    client = TestClient(app)
    payload = {"message": "Tìm phòng trọ gần Đại học UIT dưới 4 triệu"}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "text_reply" in data
    assert "session_id" in data
    assert data["session_id"] is not None


def test_ai_agent_service_chat_with_use_graph(monkeypatch):
    def mock_run_graph(user_message, session_id=None):
        return AgentResponse(
            session_id=session_id or "graph-session-456",
            text_reply="Kết quả từ LangGraph 8-node state machine.",
            rooms=[],
            insights=None,
        )

    monkeypatch.setattr("service.service.run_graph", mock_run_graph)
    client = TestClient(app)
    payload = {"message": "Tìm phòng trọ gần UIT", "use_graph": True}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "LangGraph" in data["text_reply"]
    assert data["session_id"] is not None


def test_ai_agent_service_chat_stream(monkeypatch):
    def mock_run_stream(user_message, conversation_history=None, session_id=None):
        yield 'event: text_delta\ndata: {"delta": "Chào bạn"}\n\n'
        yield 'event: done\ndata: {"session_id": "test", "text_reply": "Chào bạn", "rooms": []}\n\n'

    monkeypatch.setattr("service.service.run_stream", mock_run_stream)
    client = TestClient(app)
    payload = {"message": "Xin chào"}
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "text_delta" in response.text
