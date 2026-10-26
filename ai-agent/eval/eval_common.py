"""Tiện ích dùng chung cho các script đánh giá Homigo AI Agent.

Gom những thứ trước đây bị lặp hoặc rải rác ở cả hai script: cấu hình console UTF-8,
sys.path, phân loại trạng thái, khoảng tin cậy Wilson, percentile, chuẩn hoá tiếng Việt,
kiểm tra trace events.

Module này KHÔNG import code của dự án nên có thể test độc lập.
"""

from __future__ import annotations

import math
import re
import sys
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


# ------------------------------------------------------------------ môi trường
def setup_console() -> None:
    """Ép stdout/stderr sang UTF-8 (Windows). Gọi trong main(), không gọi lúc import."""
    if sys.platform.startswith("win"):
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:
                pass


def ensure_project_root_on_path(script_file: str | Path) -> Path:
    """Thêm thư mục cha của thư mục chứa script vào sys.path và trả về đường dẫn đó."""
    root = Path(script_file).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


# ------------------------------------------------------------------ văn bản
def fold(text: Any) -> str:
    """Chữ thường + bỏ dấu tiếng Việt (đ -> d). Dùng để so khớp không phụ thuộc dấu."""
    s = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def contains_term(folded_text: str, term: str) -> bool:
    """Tìm `term` như một từ/cụm từ nguyên vẹn (có biên từ) trong văn bản đã fold.

    Tránh lỗi substring kiểu "quan 1" khớp "quan 10" hay "gac" khớp "gach".
    """
    pattern = rf"(?<![a-z0-9]){re.escape(fold(term))}(?![a-z0-9])"
    return re.search(pattern, folded_text) is not None


def enum_value(x: Any) -> str:
    """Giá trị chuỗi của Enum (hoặc str(x)). Không dùng str(Enum) vì ra 'RoomType.X'."""
    if isinstance(x, Enum):
        return str(x.value)
    return "" if x is None else str(x)


def enum_name(x: Any) -> str:
    """Tên thành viên Enum viết hoa (vd. 'AIRCON'); với giá trị thường thì str(x).upper()."""
    if isinstance(x, Enum):
        return x.name.upper()
    return str(x).upper()


# ------------------------------------------------------------------ thống kê
def status_from_rate(rate: float, pass_at: float, warn_at: float) -> str:
    if rate >= pass_at:
        return PASS
    if rate >= warn_at:
        return WARN
    return FAIL


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy Wilson 95% cho tỷ lệ. Quan trọng khi số ca kiểm thử nhỏ."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: Sequence[float], p: float) -> float:
    """Percentile nội suy tuyến tính (p trong 0..100). Trả NaN nếu rỗng."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


# ------------------------------------------------------------------ trace
def validate_trace_events(events: Optional[Sequence[dict]]) -> list[str]:
    """Kiểm tra trace events THẬT: id duy nhất, có type, có node/tool, timestamp không lùi.

    Trả về danh sách vấn đề (rỗng = hợp lệ).
    """
    if not events:
        return ["không có sự kiện trace nào"]
    problems: list[str] = []
    seen: set[Any] = set()
    prev_ts: Optional[float] = None
    for i, ev in enumerate(events):
        eid = ev.get("id")
        if not eid:
            problems.append(f"sự kiện #{i} thiếu id")
        elif eid in seen:
            problems.append(f"id trùng: {eid}")
        else:
            seen.add(eid)
        if not ev.get("type"):
            problems.append(f"sự kiện #{i} thiếu type")
        if not (ev.get("node") or ev.get("tool")):
            problems.append(f"sự kiện #{i} thiếu node/tool")
        ts = ev.get("timestamp")
        if not isinstance(ts, (int, float)):
            problems.append(f"sự kiện #{i} timestamp không hợp lệ")
        else:
            if prev_ts is not None and ts < prev_ts:
                problems.append(f"timestamp bị lùi tại sự kiện #{i}")
            prev_ts = float(ts)
    return problems
