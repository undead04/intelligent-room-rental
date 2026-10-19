"""Security Middlewares cho FastAPI Backend:
1. SQLInjectionMiddleware: Phát hiện và ngăn chặn các hành vi tấn công SQL Injection trong query parameters và request payload.
2. RateLimitMiddleware: Giới hạn tần suất gọi API (Rate Limiting) theo địa chỉ IP để chống brute force và DoS.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Optional
from threading import Lock

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.response import ErrorDTO

logger = logging.getLogger(__name__)

# Regex phát hiện các mẫu SQL Injection nguy hiểm
SQLI_PATTERNS = [
    r"(\%27)|(\')|(\;\s*\-\-)|(\'\s*\-\-)|(\-\-\s*$)",  # Dấu nháy đơn, SQL comment cuối câu
    r"\b(union\s+(all\s+)?select)\b",   # UNION SELECT
    r"\b(select\s+.+\s+from)\b",        # SELECT ... FROM
    r"\b(insert\s+into.+values)\b",     # INSERT INTO
    r"\b(drop\s+(table|database|view|index))\b", # DROP TABLE/DATABASE
    r"\b(truncate\s+table)\b",          # TRUNCATE
    r"\b(alter\s+table)\b",             # ALTER TABLE
    r"\b(exec(\s|\+)+(s|x)p\w+)\b",     # EXEC xp_cmdshell
    r"(\b(or|and)\b\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+[\'\"]?)", # OR 1=1, AND 'a'='a'
    r";\s*--",                          # Semicolon comment
]

COMPILED_SQLI_REGEXES = [re.compile(p, re.IGNORECASE) for p in SQLI_PATTERNS]


class SQLInjectionMiddleware(BaseHTTPMiddleware):
    """Middleware kiểm tra chuỗi truy vấn (query string) và đường dẫn URL để chặn SQL Injection."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # 1. Kiểm tra raw URL query params
        raw_query = request.url.query
        if raw_query:
            for pattern in COMPILED_SQLI_REGEXES:
                if pattern.search(raw_query):
                    request_id = getattr(request.state, "request_id", "sec-blocked")
                    logger.warning(
                        "SQL Injection attempt blocked in query! client=%s path=%s query=%s",
                        request.client.host if request.client else "unknown",
                        request.url.path,
                        raw_query,
                    )
                    payload = ErrorDTO(
                        status=403,
                        code="SQL_INJECTION_DETECTED",
                        message="Yêu cầu bị từ chối do phát hiện cú pháp không an toàn (SQL Injection protection).",
                        request_id=request_id,
                    )
                    return JSONResponse(status_code=403, content=payload.model_dump())

        # 2. Kiểm tra đường dẫn path
        path = request.url.path
        for pattern in COMPILED_SQLI_REGEXES:
            if pattern.search(path):
                request_id = getattr(request.state, "request_id", "sec-blocked")
                logger.warning(
                    "SQL Injection attempt blocked in path! client=%s path=%s",
                    request.client.host if request.client else "unknown",
                    path,
                )
                payload = ErrorDTO(
                    status=403,
                    code="SQL_INJECTION_DETECTED",
                    message="Yêu cầu bị từ chối do phát hiện cú pháp không an toàn trong đường dẫn.",
                    request_id=request_id,
                )
                return JSONResponse(status_code=403, content=payload.model_dump())

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware giới hạn tần suất yêu cầu (Sliding Window Rate Limiter) theo IP."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 120,
        enabled: bool = True,
        whitelist_paths: Optional[set[str]] = None,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.enabled = enabled
        self.whitelist_paths = whitelist_paths or {"/docs", "/openapi.json", "/redoc", "/api/v1/health", "/"}
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Bỏ qua các path nằm trong whitelist (Swagger Docs, Health check)
        if request.url.path in self.whitelist_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        window_start = now - 60.0

        with self._lock:
            # Dọn dẹp các bản ghi cũ hơn 60 giây
            timestamps = [t for t in self._history[client_ip] if t > window_start]
            
            if len(timestamps) >= self.requests_per_minute:
                # Quá số lượng yêu cầu cho phép trong 1 phút
                oldest = timestamps[0]
                retry_after = max(1, int(60.0 - (now - oldest)))
                request_id = getattr(request.state, "request_id", "rate-limited")
                logger.warning(
                    "Rate limit exceeded for IP=%s on path=%s. Count=%d/min",
                    client_ip,
                    request.url.path,
                    len(timestamps),
                )
                payload = ErrorDTO(
                    status=429,
                    code="RATE_LIMIT_EXCEEDED",
                    message=f"Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau {retry_after} giây.",
                    request_id=request_id,
                )
                return JSONResponse(
                    status_code=429,
                    content=payload.model_dump(),
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            # Ghi nhận lượt gọi mới
            timestamps.append(now)
            self._history[client_ip] = timestamps
            remaining = self.requests_per_minute - len(timestamps)

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
