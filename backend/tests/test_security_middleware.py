"""Unit tests cho Security Middlewares của FastAPI Backend:
- SQLInjectionMiddleware
- RateLimitMiddleware
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.security_middleware import RateLimitMiddleware, SQLInjectionMiddleware


def create_test_app(requests_per_minute: int = 5):
    test_app = FastAPI()
    test_app.add_middleware(SQLInjectionMiddleware, enabled=True)
    test_app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=requests_per_minute,
        enabled=True,
        whitelist_paths={"/whitelist"},
    )

    @test_app.get("/items")
    def get_items(search: str = ""):
        return {"ok": True, "search": search}

    @test_app.get("/whitelist")
    def get_whitelist():
        return {"status": "ok"}

    return test_app


def test_sql_injection_middleware_blocks_malicious_query():
    app = create_test_app()
    client = TestClient(app)

    malicious_queries = [
        "' OR '1'='1",
        "1 UNION SELECT null, username, password FROM users --",
        "'; DROP TABLE listings; --",
    ]

    for q in malicious_queries:
        resp = client.get(f"/items?search={q}")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "SQL_INJECTION_DETECTED"


def test_sql_injection_middleware_allows_normal_query():
    app = create_test_app()
    client = TestClient(app)

    resp = client.get("/items?search=phong tro linh xuan gia re")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_rate_limit_middleware_enforces_limit():
    app = create_test_app(requests_per_minute=3)
    client = TestClient(app)

    # 3 requests đầu tiên thành công
    for _ in range(3):
        resp = client.get("/items")
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers

    # Request thứ 4 phải bị chặn với mã 429
    blocked_resp = client.get("/items")
    assert blocked_resp.status_code == 429
    assert blocked_resp.json()["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in blocked_resp.headers


def test_rate_limit_whitelist_bypasses_limiter():
    app = create_test_app(requests_per_minute=2)
    client = TestClient(app)

    # Gọi 5 lần vào whitelist path mà không bị chặn
    for _ in range(5):
        resp = client.get("/whitelist")
        assert resp.status_code == 200
