"""Tiện ích dùng chung cho các script của skill search-room (chỉ dùng stdlib)."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Lấy Base URL và Timeout từ Environment Variables (mặc định localhost:8000/api/v1)
BASE_URL = os.environ.get("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
TIMEOUT = float(os.environ.get("SEARCH_ROOM_TIMEOUT", "30"))


def setup_utf8() -> None:
    """Khắc phục lỗi mã hóa tiếng Việt trên Windows (cp1252/cp936).
    Ép stdout và stderr dùng encoding utf-8 để Agent hoặc Terminal đọc đúng ký tự.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def emit(obj) -> None:
    """In dữ liệu ra stdout dạng JSON được format đẹp (indent=2) và giữ nguyên UTF-8.
    Đây là đầu ra tiêu chuẩn để AI Agent parse dữ liệu.
    """
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(message, detail=None, status=None):
    """In thông báo lỗi chuẩn hóa dạng JSON ra stdout rồi dừng chương trình với exit code 1.
    Giúp Agent nhận biết ngay script bị thất bại và lấy được lý do cụ thể.
    """
    emit({"ok": False, "status": status, "error": message, "detail": detail})
    sys.exit(1)


def build_url(path, params=None):
    """Lắp ráp URL hoàn chỉnh và tự động lọc bỏ các query param có giá trị None.
    
    Ví dụ: build_url("/wards", {"district_id": 5, "name": None})
    -> "http://localhost:8000/api/v1/wards?district_id=5"
    """
    url = f"{BASE_URL}{path}"
    # Lọc bỏ các key có v is None trước khi encode
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    if clean:
        url += "?" + urllib.parse.urlencode(clean, doseq=True)
    return url


def request(method, path, params=None, body=None):
    """Hàm wrapper thực hiện HTTP request dùng urllib (stdlib).
    
    - Tự động serialize body sang JSON nếu có.
    - Bắt toàn bộ lỗi HTTP (4xx, 5xx), lỗi kết nối (Timeout, Connection Refused) 
      và parse lỗi trả về cho hàm fail().
    """
    url = build_url(path, params)
    headers = {"Accept": "application/json"}
    data = None
    
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
            
    except urllib.error.HTTPError as e:
        # Xử lý khi Backend trả về mã lỗi HTTP (400, 404, 500,...)
        raw = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = raw
        fail(f"HTTP {e.code} từ {method} {url}", detail, status=e.code)
        
    except urllib.error.URLError as e:
        # Xử lý lỗi mạng / server chưa bật
        fail(f"Không kết nối được tới {url}. Backend đã chạy chưa?", str(e.reason))
        
    except ValueError:
        # Server trả về 200 OK nhưng body không phải JSON
        fail(f"Phản hồi từ {url} không phải JSON hợp lệ")


def unwrap(payload):
    """Bóc tách dữ liệu nếu Backend dùng chuẩn ResponseDTO dạng:
    {
       "success": true,
       "status": 200,
       "data": { ... },
       "message": "OK"
    }
    
    Nếu success = false -> Gọi fail() ngay lập tức.
    Nếu không đúng wrapper chuẩn -> Trả về nguyên gốc payload.
    """
    if isinstance(payload, dict) and "data" in payload and "success" in payload:
        if payload.get("success") is False:
            fail(payload.get("message") or "API trả về success=false", payload,
                 status=payload.get("status"))
        return payload["data"]
    return payload


def strip_keys(obj, needles=("embedding", "vector")):
    """Đệ quy duyệt dict/list để xóa các field chứa vector/embedding (ví dụ pgvector).
    
    Mục đích: Mảng vector thường chứa hàng trăm/nghìn số thực (float), 
    nếu in ra sẽ tốn rất nhiều Context Window của LLM/Agent mà không mang lại giá trị đọc hiểu.
    """
    if isinstance(obj, dict):
        return {k: strip_keys(v, needles) for k, v in obj.items()
                if not any(n in k.lower() for n in needles)}
    if isinstance(obj, list):
        return [strip_keys(i, needles) for i in obj]
    return obj