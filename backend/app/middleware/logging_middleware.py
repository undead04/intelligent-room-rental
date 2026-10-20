from __future__ import annotations

import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware gắn request_id duy nhất và ghi log chi tiết cho từng request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error request_id=%s path=%s",
                request_id,
                request.url.path,
            )
            raise

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
