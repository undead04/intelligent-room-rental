"""Backward compatibility shim.
Vị trí chính thức: `crawler.model.llm.client`
"""
from crawler.model.llm.client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RPM_DELAY,
    GeminiRoundRobin,
    call_gemini_chunk,
    is_quota_error,
)

__all__ = [
    "GeminiRoundRobin",
    "call_gemini_chunk",
    "is_quota_error",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RPM_DELAY",
]
