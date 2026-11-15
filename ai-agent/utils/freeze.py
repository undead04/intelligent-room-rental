"""Tiện ích đóng băng đệ quy cấu trúc dữ liệu (Immutable Deep Freeze)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


def deep_freeze(obj: Any) -> Any:
    """Đóng băng đệ quy cấu trúc dict/list/set thành MappingProxyType/tuple bất biến cho Verifier."""
    if isinstance(obj, Mapping):
        return MappingProxyType({k: deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple, set, frozenset)):
        return tuple(deep_freeze(item) for item in obj)
    return obj
