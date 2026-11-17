"""Điểm tạo LLM DUY NHẤT của dự án (1 Cloud model duy nhất).

  get_llm()                                 -> mặc định LLM_GENERATION_TEMPERATURE (0.3) cho sinh văn bản tư vấn
  get_llm(temperature=LLM_NLU_TEMPERATURE)  -> 0.0 cho NLU & Critic có cấu trúc (0.3 khi NLU retry).

Import langchain_openai TRONG hàm để file này không kéo theo vòng import và test được mà không cần cài gói.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from core.config import LLM_GENERATION_TEMPERATURE, Settings, load_settings

logger = logging.getLogger(__name__)


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
    "get_llm",
    "reset_llm_cache",
]
