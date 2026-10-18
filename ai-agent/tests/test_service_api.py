from fastapi.testclient import TestClient
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


def test_ai_agent_service_chat_valid_query():
    client = TestClient(app)
    payload = {"message": "Tìm phòng trọ gần Đại học UIT dưới 4 triệu"}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "text_reply" in data
    assert "session_id" in data
    assert data["session_id"] is not None
