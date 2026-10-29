"""Quản lý biến môi trường và cấu hình hệ thống cho Homigo AI Agent (Pydantic Settings)."""

from __future__ import annotations

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from core import paths

PROJECT_NAME = "homigo-housing-agent"
APP_TITLE = "Homigo AI Agent: Observability & Debug Console"
CAPABILITY_TEXT = (
    "Tools: search_rooms, geocode_location, get_location_hierarchy, get_listing_detail, consult_housing_skill. "
    "Quan sát trực tiếp Tool execution, Trọng số Intent MCDM, Traces và Context Window token breakdown."
)

# Giới hạn số lần gọi model trong một lượt chat (ModelCallLimitMiddleware).
MODEL_CALL_LIMIT = 8
# Giới hạn số tool calls trong một lượt chat (ToolCallLimitMiddleware).
TOOL_CALL_LIMIT = 20
# Giới hạn số bước của LangGraph (recursion limit), không phải số tool calls.
RECURSION_LIMIT = 50


class Settings(BaseModel):
    """Pydantic Configuration Settings cho Homigo AI Agent."""

    api_key: str = Field(default="", description="API Key của OpenAI hoặc Gemini")
    model_name: str = Field(default="gpt-4o-mini", description="Tên model LLM sử dụng")
    fast_model_name: Optional[str] = Field(default=None, description="Tên model LLM nhanh (nếu tách riêng)")
    enable_main_thinking: bool = Field(default=True, description="Bật chế độ suy nghĩ (Thinking) cho role 'main'")
    enable_prompt_caching: bool = Field(default=True, description="Bật cơ chế tối ưu Prefix/KV-Cache Caching")
    kv_cache_type: str = Field(default="q8_0", description="Kiểu lượng tử hóa KV-Cache khuyến nghị: q8_0, q4_0, fp16")
    base_url: Optional[str] = Field(default=None, description="Endpoint URL tùy chỉnh (nếu có)")
    search_room_api_base: str = Field(
        default="http://localhost:8000/api/v1",
        description="URL cơ sở của Backend FastAPI",
    )
    search_room_timeout: float = Field(default=20.0, description="Timeout HTTP gọi Backend (giây)")
    llm_timeout: float = Field(default=60.0, description="Timeout gọi LLM (giây)")
    llm_max_retries: int = Field(default=1, description="Số lần retry khi gọi LLM gặp sự cố")
    host: str = Field(default="127.0.0.1", description="Host khởi chạy Uvicorn")
    port: int = Field(default=8001, description="Port khởi chạy Uvicorn")
    env: str = Field(default="development", description="Môi trường vận hành")

    model_config = {"frozen": True, "extra": "ignore"}


def load_settings() -> tuple[Settings | None, list[str]]:
    """Đọc .env của project này. Trả (settings, []) hoặc (None, danh sách biến còn thiếu)."""
    load_dotenv(paths.ENV_PATH, override=False)
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip() or "gpt-4o-mini"
    fast_model_name = os.getenv("FAST_MODEL_NAME", "").strip() or None
    enable_main_thinking = os.getenv("ENABLE_MAIN_THINKING", "true").strip().lower() in ("1", "true", "yes", "on")
    enable_prompt_caching = os.getenv("ENABLE_PROMPT_CACHING", "true").strip().lower() in ("1", "true", "yes", "on")
    kv_cache_type = os.getenv("KV_CACHE_TYPE", "q8_0").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    api_base = os.getenv("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
    timeout = float(os.getenv("SEARCH_ROOM_TIMEOUT", "20.0"))
    llm_timeout = float(os.getenv("LLM_TIMEOUT", "60.0"))
    llm_max_retries = int(os.getenv("LLM_MAX_RETRIES", "1"))
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8001"))
    env = os.getenv("ENV", "development")

    missing = []
    if not api_key:
        missing.append("OPENAI_API_KEY (hoặc GEMINI_API_KEY)")
    if missing:
        return None, missing

    return (
        Settings(
            api_key=api_key,
            model_name=model_name,
            fast_model_name=fast_model_name,
            enable_main_thinking=enable_main_thinking,
            enable_prompt_caching=enable_prompt_caching,
            kv_cache_type=kv_cache_type,
            base_url=base_url,
            search_room_api_base=api_base,
            search_room_timeout=timeout,
            llm_timeout=llm_timeout,
            llm_max_retries=llm_max_retries,
            host=host,
            port=port,
            env=env,
        ),
        [],
    )
