"""Đường dẫn của project, resolve từ vị trí file này (không phụ thuộc thư mục terminal)."""

from pathlib import Path

# Vị trí: ai-agent/core/paths.py -> parent là core/, parent.parent là ai-agent/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "sessions.db"
TRACES_DIR = PROJECT_ROOT / "traces"
SKILLS_DIR = PROJECT_ROOT / "skills"
OUTPUT_SUBDIR = "traces"

__all__ = [
    "PROJECT_ROOT",
    "ENV_PATH",
    "DATA_DIR",
    "DEFAULT_DB_PATH",
    "TRACES_DIR",
    "SKILLS_DIR",
    "OUTPUT_SUBDIR",
]
