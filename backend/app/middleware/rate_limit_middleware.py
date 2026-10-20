from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from threading import Lock
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.response import ErrorDTO

logger = logging.getLogger(__name__)


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
        self._cleanup_counter = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Bỏ qua các path nằm trong whitelist (Swagger Docs, Health check)
        if request.url.path in self.whitelist_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        window_start = now - 60.0

        with self._lock:
            # Định kỳ dọn sạch toàn bộ dictionary để giải phóng RAM các IP cũ
            self._cleanup_counter += 1
            if self._cleanup_counter >= 200:
                self._cleanup_counter = 0
                stale_ips = [ip for ip, times in self._history.items() if not times or times[-1] <= window_start]
                for ip in stale_ips:
                    del self._history[ip]

            # Dọn dẹp các bản ghi cũ hơn 60 giây của IP hiện tại
            timestamps = [t for t in self._history[client_ip] if t > window_start]

            if len(timestamps) >= self.requests_per_minute:
                # Quá số lượng yêu cầu cho phép trong 1 phút
                oldest = timestamps[0]
                retry_after = max(1, int(60.0 - (now - oldest)))
                request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
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
                        "X-Request-ID": request_id,
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
