"""HTTP dùng chung cho các tool: MỘT httpx.Client tái sử dụng (kết nối giữ sống), không tạo client mới mỗi lần gọi."""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

import httpx

API_BASE = os.environ.get("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
TIMEOUT = float(os.environ.get("SEARCH_ROOM_TIMEOUT", "20.0"))

_client: Optional[httpx.Client] = None
_lock = threading.Lock()


def get_client() -> httpx.Client:
    global _client
    with _lock:
        if _client is None or _client.is_closed:
            _client = httpx.Client(base_url=API_BASE, timeout=TIMEOUT, follow_redirects=True)
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
        return {"ok": False, "error": f"Phản hồi không phải JSON ({preview})"}
    if resp.is_error:
        msg = data.get("message") if isinstance(data, dict) else None
        return {"ok": False, "error": msg or f"HTTP {resp.status_code}", "status": resp.status_code}
    if isinstance(data, dict) and "success" in data:          # phong bì {"success", "data"?, "message"?}; bản cũ đòi có cả "data" nên lỗi không kèm data bị coi là thành công
        if not data.get("success", False):
            return {"ok": False, "error": data.get("message") or "API trả về lỗi"}
        return {"ok": True, "data": data.get("data")}
    return {"ok": True, "data": data}


def request(method: str, path: str, *, params: Optional[dict] = None, json: Optional[dict] = None) -> dict[str, Any]:
    """Gọi API, KHÔNG BAO GIỜ ném lỗi: lỗi mạng -> {"ok": False, "error": ...}."""
    try:
        resp = get_client().request(method, path, params=params, json=json)
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Không thể kết nối đến {API_BASE}{path}: {e}"}
    return unwrap_response(resp)
