"""Điểm tạo LLM DUY NHẤT của dự án (thay _get_llm trong graph, _get_tools_llm trong tools, build_model trong agent).

  get_llm("main")  -> tư vấn, viết câu trả lời (bật Thinking cho Gemma-4-E4B để phân tích sâu)
  get_llm("fast")  -> phân loại / chuẩn hoá / NLU (tắt Thinking để phản hồi nhanh, temperature 0).

Import langchain_openai TRONG hàm để file này không kéo theo vòng import và test được mà không cần cài gói.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:  # pragma: no cover
    from langchain_openai import ChatOpenAI

    from core.config import Settings

logger = logging.getLogger(__name__)

Role = Literal["main", "fast"]

REQUEST_TIMEOUT_S = 60
MAX_RETRIES = 2


def build_model(settings: "Settings", role: Role = "main") -> "ChatOpenAI":
    from langchain_openai import ChatOpenAI

    fast_name = getattr(settings, "fast_model_name", None)
    enable_thinking = bool(getattr(settings, "enable_main_thinking", True)) if role == "main" else False
    max_retries = getattr(settings, "llm_max_retries", MAX_RETRIES)

    kwargs = {
        "model": (fast_name if role == "fast" and fast_name else settings.model_name),
        "api_key": settings.api_key,
        "timeout": getattr(settings, "llm_timeout", REQUEST_TIMEOUT_S) or REQUEST_TIMEOUT_S,
        "max_retries": max_retries if max_retries is not None else MAX_RETRIES,
        "temperature": 0 if role == "fast" else 0.3,
        "extra_body": {
            "enable_thinking": enable_thinking,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        },
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)


@lru_cache(maxsize=2)
def _cached(role: Role) -> Optional["ChatOpenAI"]:
    try:
        from core.config import load_settings

        settings, _ = load_settings()
        return build_model(settings, role) if settings else None
    except Exception:
        logger.exception("Không khởi tạo được LLM (%s)", role)
        return None


def get_llm(role: Role = "main") -> Optional["ChatOpenAI"]:
    """Trả LLM đã cache theo vai trò; None nếu chưa cấu hình/lỗi (caller dùng đường fallback)."""
    return _cached(role)


def reset_llm_cache() -> None:
    """Dùng khi đổi cấu hình lúc chạy, hoặc trong test."""
    _cached.cache_clear()


__all__ = [
    "Role",
    "REQUEST_TIMEOUT_S",
    "MAX_RETRIES",
    "build_model",
    "get_llm",
    "reset_llm_cache",
]
