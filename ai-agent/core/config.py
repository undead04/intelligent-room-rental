"""Quản lý biến môi trường và cấu hình tập trung (SSOT) cho Homigo AI Agent."""

from __future__ import annotations

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from core import paths

# =============================================================================
# Cấu hình LLM & Vòng gọi Agent (Cloud-Native)
# =============================================================================
MODEL_CALL_LIMIT = 8
TOOL_CALL_LIMIT = 20
LLM_GENERATION_TEMPERATURE = 0.3  # Sinh câu trả lời tự nhiên (decision / advisory / clarification)
LLM_NLU_TEMPERATURE = 0.0         # Mặc định 0.0 cho NLU (bóc tách JSON ổn định) & Critic
LLM_NLU_RETRY_TEMPERATURE = 0.3   # Chỉ nâng NLU lên 0.3 khi retry

# =============================================================================
# Cấu hình Tìm kiếm, Bán kính & Phân trang (Search / Retrieval / Pagination)
# =============================================================================
DEFAULT_SEARCH_LIMIT = 5
MAX_PAGINATION_PAGES = 10
DEFAULT_PAGE_SIZE = DEFAULT_SEARCH_LIMIT
MAX_PAGED_ROOMS = DEFAULT_PAGE_SIZE * MAX_PAGINATION_PAGES
MAX_SEARCH_LIMIT = MAX_PAGED_ROOMS

NEARBY_AREAS_LIMIT = 4
NEARBY_FALLBACK_LIMIT = 3

DEFAULT_RADIUS_KM = 3.0
DEFAULT_ADAPTIVE_RADII_KM = (5.0, 7.0)
BROAD_AREA_RADIUS_KM = 4.0
BROAD_AREA_ADAPTIVE_RADII_KM = (5.0, 6.5)

# =============================================================================
# Cấu hình Phiên hội thoại (Session Store)
# =============================================================================
MAX_SESSION_MESSAGES = 20
HISTORY_WINDOW = 8
MAX_SESSIONS = 500
SESSION_TTL_SECONDS = 86_400

# =============================================================================
# Cấu hình Retry cho HTTP & Định vị (Tools / Location)
# =============================================================================
HTTP_MAX_RETRIES = 1
HTTP_RETRY_BACKOFF_SECONDS = 0.25
RESOLVE_LOCATION_MAX_RETRIES = 2


class Settings(BaseModel):
    """Pydantic Configuration Settings cho Homigo AI Agent."""

    api_key: str = Field(default="", description="API Key của Cloud LLM (Gemini / OpenAI)")
    model_name: str = Field(default="gpt-4o-mini", description="Tên model Cloud LLM duy nhất sử dụng")
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
    cors_allowed_origins: tuple[str, ...] = Field(
        default=("http://localhost:3000", "http://127.0.0.1:3000"),
        description="Danh sách origin được phép CORS",
    )

    model_config = ConfigDict(frozen=True, extra="ignore")


def _parse_cors_origins() -> tuple[str, ...]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ("http://localhost:3000", "http://127.0.0.1:3000")
    parsed = tuple(o.strip() for o in raw.split(",") if o.strip())
    return parsed or ("http://localhost:3000", "http://127.0.0.1:3000")


def get_runtime_settings() -> Settings:
    """Đọc toàn bộ cấu hình hạ tầng từ `.env` / môi trường (không fail khi thiếu API key)."""
    load_dotenv(paths.ENV_PATH, override=False)
    return Settings(
        api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        model_name=os.getenv("MODEL_NAME", "").strip() or "gpt-4o-mini",
        base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
        search_room_api_base=os.getenv("SEARCH_ROOM_API_BASE", "http://localhost:8000/api/v1").rstrip("/"),
        search_room_timeout=float(os.getenv("SEARCH_ROOM_TIMEOUT", "20.0")),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "60.0")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "1")),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8001")),
        env=os.getenv("ENV", "development"),
        cors_allowed_origins=_parse_cors_origins(),
    )


def load_settings() -> tuple[Settings | None, list[str]]:
    """Đọc .env của project này. Trả (settings, []) hoặc (None, danh sách biến còn thiếu)."""
    settings = get_runtime_settings()
    missing = []
    if not settings.api_key:
        missing.append("OPENAI_API_KEY")
    if missing:
        return None, missing
    return settings, []
