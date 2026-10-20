from __future__ import annotations

import logging
import re
import uuid
from urllib.parse import unquote_plus
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.response import ErrorDTO

logger = logging.getLogger(__name__)

# Regex phát hiện các mẫu SQL Injection nguy hiểm
SQLI_PATTERNS = [
    r"(\%27|\')\s*(\b(or|and)\b|--|\;)",             # Nháy đơn kèm mệnh đề OR/AND hoặc comment
    r"(\b(or|and)\b\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+[\'\"]?)", # OR 1=1, AND 'a'='a'
    r"\b(union\s+(all\s+)?select)\b",                # UNION SELECT
    r"\b(select\s+.+\s+from)\b",                     # SELECT ... FROM
    r"\b(insert\s+into.+values)\b",                  # INSERT INTO
    r"\b(drop\s+(table|database|view|index))\b",      # DROP TABLE/DATABASE
    r"\b(truncate\s+table)\b",                       # TRUNCATE TABLE
    r"\b(alter\s+table)\b",                          # ALTER TABLE
    r"\b(exec(\s|\+)+(s|x)p\w+)\b",                  # EXEC xp_cmdshell
    r";\s*--",                                       # Semicolon comment
    r"--\s*$",                                       # Comment cuối dòng
]

COMPILED_SQLI_REGEXES = [re.compile(p, re.IGNORECASE) for p in SQLI_PATTERNS]


class SQLInjectionMiddleware(BaseHTTPMiddleware):
    """Middleware kiểm tra chuỗi truy vấn (query string) và đường dẫn URL để chặn SQL Injection."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    def _matches_sqli(self, text: str) -> bool:
        if not text:
            return False
        # Kiểm tra cả chuỗi nguyên bản và chuỗi đã decode URL
        decoded = unquote_plus(text)
        for pattern in COMPILED_SQLI_REGEXES:
            if pattern.search(text) or pattern.search(decoded):
                return True
        return False

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # 1. Kiểm tra raw URL query params
        raw_query = request.url.query
        if self._matches_sqli(raw_query):
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
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
            return JSONResponse(
                status_code=403,
                content=payload.model_dump(),
                headers={"X-Request-ID": request_id},
            )

        # 2. Kiểm tra đường dẫn path
        path = request.url.path
        if self._matches_sqli(path):
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
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
            return JSONResponse(
                status_code=403,
                content=payload.model_dump(),
                headers={"X-Request-ID": request_id},
            )

        return await call_next(request)
