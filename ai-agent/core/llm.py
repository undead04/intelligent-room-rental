"""Điểm tạo LLM DUY NHẤT của dự án (1 Cloud model duy nhất).

  get_llm()                                 -> mặc định LLM_GENERATION_TEMPERATURE (0.3) cho sinh văn bản tư vấn
  get_llm(temperature=LLM_NLU_TEMPERATURE)  -> 0.0 cho NLU & Critic có cấu trúc (0.3 khi NLU retry).

Import langchain_openai TRONG hàm để file này không kéo theo vòng import và test được mà không cần cài gói.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any, Callable, Optional, TypeVar

from langchain_openai import ChatOpenAI

from core.config import LLM_GENERATION_TEMPERATURE, Settings, load_settings

logger = logging.getLogger(__name__)
T = TypeVar("T")

_DAILY_QUOTA_MARKERS = (
    "resource_exhausted",
    "generaterequestsperday",
    "requests per day limit exceeded",
    "free_tier_requests",
    "quota exceeded for metric",
    "exceeded your current quota",
)
_OVERLOAD_RATE_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "503",
    "unavailable",
    "high demand",
    "overloaded",
    "502",
    "504",
    "bad gateway",
    "service unavailable",
)
_CONNECTION_TRANSIENT_MARKERS = (
    "connection",
    "timeout",
    "timed out",
    "reset by peer",
    "remote end closed",
)


def is_daily_quota_exhausted(err_msg: str) -> bool:
    """Nhận diện lỗi cạn hạn mức ngày (Daily Quota) của Google Gemini / OpenAI."""
    low = (err_msg or "").lower()
    return any(kw in low for kw in _DAILY_QUOTA_MARKERS)


def classify_llm_retry_delay(exc: BaseException, attempt: int) -> Optional[float]:
    """Trả về số giây chờ retry nếu lỗi là quá tải/429 RPM/503/mạng tạm thời; None nếu không nên retry."""
    err_msg = str(exc).lower()
    if is_daily_quota_exhausted(err_msg):
        return None
    if any(marker in err_msg for marker in _OVERLOAD_RATE_MARKERS):
        return 2.0 * (attempt + 1)
    if any(marker in err_msg for marker in _CONNECTION_TRANSIENT_MARKERS):
        return 0.5
    return None


def invoke_with_retry(
    call: Callable[[], T],
    *,
    max_attempts: int = 3,
    context: str = "llm",
) -> T:
    """Gọi hàm LLM kèm retry backoff cho lỗi tạm thời (503 high demand, 429 RPM, lỗi mạng)."""
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            delay = classify_llm_retry_delay(exc, attempt)
            if delay is not None and attempt < attempts - 1:
                logger.warning(
                    "%s gặp lỗi tạm thời (%s), chờ %.1fs rồi thử lại lần %d/%d...",
                    context,
                    type(exc).__name__,
                    delay,
                    attempt + 1,
                    attempts - 1,
                )
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("invoke_with_retry unreachable")


def build_model(settings: "Settings", *, temperature: Optional[float] = None) -> "ChatOpenAI":
    eff_temp = LLM_GENERATION_TEMPERATURE if temperature is None else float(temperature)
    kwargs: dict[str, Any] = {
        "model": getattr(settings, "model_name"),
        "api_key": settings.api_key,
        "timeout": getattr(settings, "llm_timeout"),
        "max_retries": getattr(settings, "llm_max_retries"),
        "temperature": eff_temp,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)


@lru_cache(maxsize=4)
def _cached(temperature: float) -> Optional["ChatOpenAI"]:
    try:
        settings, _ = load_settings()
        return build_model(settings, temperature=temperature) if settings else None
    except Exception:
        logger.exception("Không khởi tạo được LLM (temperature=%s)", temperature)
        return None


def get_llm(temperature: Optional[float] = None) -> Optional["ChatOpenAI"]:
    """Trả về 1 Cloud LLM duy nhất đã cache theo temperature; None nếu chưa cấu hình/lỗi."""
    eff_temp = LLM_GENERATION_TEMPERATURE if temperature is None else float(temperature)
    return _cached(eff_temp)


def reset_llm_cache() -> None:
    """Dùng khi đổi cấu hình lúc chạy, hoặc trong test."""
    _cached.cache_clear()


__all__ = [
    "build_model",
    "classify_llm_retry_delay",
    "get_llm",
    "invoke_with_retry",
    "is_daily_quota_exhausted",
    "reset_llm_cache",
]
