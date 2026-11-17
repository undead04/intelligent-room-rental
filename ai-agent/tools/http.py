"""HTTP dùng chung cho các tool: MỘT httpx.Client tái sử dụng (kết nối giữ sống), kèm retry nhẹ cho lỗi transient."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import httpx

from core.config import (
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF_SECONDS,
    get_runtime_settings,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = frozenset({502, 503, 504})

_client: Optional[httpx.Client] = None
_lock = threading.Lock()


def _api_config() -> tuple[str, float]:
    s = get_runtime_settings()
    return s.search_room_api_base, s.search_room_timeout


def get_client() -> httpx.Client:
    global _client
    with _lock:
        if _client is None or _client.is_closed:
            api_base, timeout = _api_config()
            _client = httpx.Client(base_url=api_base, timeout=timeout, follow_redirects=True)
        return _client


def set_client(client: Optional[httpx.Client]) -> None:
    """Thay client (test với MockTransport, hoặc cấu hình riêng). None = tạo lại lần sau."""
    global _client
    with _lock:
        _client = client


def unwrap_response(resp: httpx.Response) -> dict[str, Any]:
    """Chuẩn hoá phản hồi backend về {"ok": bool, "data"?/"error"?}."""
    if resp.status_code == 404:
        return {"ok": False, "error": "Không tìm thấy dữ liệu (HTTP 404)", "status": 404}
    try:
        data = resp.json()
    except Exception:
        preview = resp.text[:200].strip() if resp.text else f"status {resp.status_code}"
        return {"ok": False, "error": f"Phản hồi không phải JSON ({preview})", "status": resp.status_code}
    if resp.is_error:
        msg = data.get("message") if isinstance(data, dict) else None
        return {"ok": False, "error": msg or f"HTTP {resp.status_code}", "status": resp.status_code}
    if isinstance(data, dict) and "success" in data:
        if not data.get("success", False):
            return {"ok": False, "error": data.get("message") or "API trả về lỗi"}
        return {"ok": True, "data": data.get("data")}
    return {"ok": True, "data": data}


def request(method: str, path: str, *, params: Optional[dict] = None, json: Optional[dict] = None) -> dict[str, Any]:
    """Gọi API có retry cho lỗi mạng/timeout/5xx (tối đa HTTP_MAX_RETRIES lần), KHÔNG BAO GIỜ ném lỗi."""
    max_retries = max(0, int(HTTP_MAX_RETRIES))
    for attempt in range(max_retries + 1):
        try:
            resp = get_client().request(method, path, params=params, json=json)
        except httpx.HTTPError as e:
            if attempt < max_retries and isinstance(e, (httpx.TimeoutException, httpx.TransportError)):
                logger.warning("HTTP %s %s lỗi kết nối (lần %d), thử lại...", method, path, attempt + 1)
                time.sleep(HTTP_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            api_base, _ = _api_config()
            return {"ok": False, "error": f"Không thể kết nối đến {api_base}{path}: {e}", "network_error": True}

        if resp.status_code in _RETRYABLE_STATUSES and attempt < max_retries:
            logger.warning("HTTP %s %s trả %s (lần %d), thử lại...", method, path, resp.status_code, attempt + 1)
            time.sleep(HTTP_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue
        res = unwrap_response(resp)
        if resp.status_code in _RETRYABLE_STATUSES:
            res["network_error"] = True
        return res

    return {"ok": False, "error": f"Không thể kết nối đến {path}", "network_error": True}
