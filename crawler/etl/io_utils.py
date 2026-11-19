"""Tiện ích đọc/ghi file trung gian JSONL dùng chung giữa các module ETL độc lập."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

_DATETIME_FIELDS = ("posted_date", "crawled_at", "last_checked_at")


def _json_default(obj: Any) -> Any:
    """Chuyển đổi các kiểu Python không chuẩn JSON (datetime, Path) khi serialize."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def write_jsonl(path: Union[str, Path], records: Iterable[Dict[str, Any]]) -> Path:
    """Ghi danh sách bản ghi ra file JSONL nguyên tử qua file tạm + os.replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, default=_json_default) + "\n")
        os.replace(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return target


def read_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Đọc toàn bộ bản ghi từ file JSONL trung gian."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Không tìm thấy file trung gian JSONL: {target}")

    records: List[Dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Lỗi cú pháp JSON tại {target}:{line_no}: {exc}") from exc
            if isinstance(obj, dict):
                records.append(obj)
    return records


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    """Khôi phục datetime từ chuỗi ISO hoặc giữ nguyên nếu đã là datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def restore_record_datetimes(record: Dict[str, Any]) -> Dict[str, Any]:
    """Trả về bản sao record với các trường thời gian đã được khôi phục về datetime."""
    restored = dict(record)
    for field in _DATETIME_FIELDS:
        if field in restored and restored[field] is not None:
            parsed = _parse_iso_datetime(restored[field])
            if parsed is not None:
                restored[field] = parsed
    return restored
