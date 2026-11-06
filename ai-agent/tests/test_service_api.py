from fastapi.testclient import TestClient
from domain.schemas import AgentResponse, UserPreferenceState
from api.routes import app


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


def test_ai_agent_service_delete_session():
    client = TestClient(app)
    response = client.delete("/api/v1/session/test-session-to-delete")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["session_id"] == "test-session-to-delete"


def test_ai_agent_service_chat_valid_query(monkeypatch):
    def mock_run(user_message, conversation_history=None, session_id=None, **kwargs):
        return AgentResponse(
            session_id=session_id or "test-session-123",
            text_reply="Tìm thấy các phòng trọ phù hợp gần Đại học UIT dưới 4 triệu.",
            rooms=[],
            insights=None,
            current_preferences=UserPreferenceState(max_price=4000000, location_text="Đại học UIT"),
            need_clarification=False,
            follow_up_questions=[],
        )

    monkeypatch.setattr("api.routes.service.run", mock_run)
    client = TestClient(app)
    payload = {"message": "Tìm phòng trọ gần Đại học UIT dưới 4 triệu"}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "text_reply" in data
    assert "session_id" in data
    assert data["session_id"] is not None


def test_ai_agent_service_chat_stream(monkeypatch):
    def mock_run_stream(user_message, conversation_history=None, session_id=None, **kwargs):
        yield "event: message\ndata: {\"type\": \"text_delta\", \"delta\": \"Xin chào\"}\n\n"
        yield "event: complete\ndata: {\"type\": \"complete\", \"text_reply\": \"Xin chào bạn\"}\n\n"

    monkeypatch.setattr("api.routes.service.run_stream", mock_run_stream)
    client = TestClient(app)
    payload = {"message": "Xin chào"}
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert "text_delta" in body
