"""Quản lý tập trung toàn bộ đường dẫn thư mục và tập tin trong module Crawler & Dự án.

Giúp chuẩn hóa và tái sử dụng, loại bỏ việc lặp lại mã nguồn tính toán đường dẫn tương đối.
"""

import sys
from pathlib import Path

# ==============================================================================
# 1. THƯ MỤC CỐT LÕI (CORE DIRECTORIES)
# ==============================================================================

# Thư mục module Crawler: .../crawler
CRAWLER_DIR = Path(__file__).resolve().parent.parent

# Thư mục gốc toàn bộ dự án: .../Đồ Án tốt nghiệp
PROJECT_ROOT = CRAWLER_DIR.parent

# Tự động đảm bảo PROJECT_ROOT luôn có mặt trong sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ==============================================================================
# 2. KHU VỰC DỮ LIỆU (DATA DIRECTORIES)
# ==============================================================================

DATA_DIR = CRAWLER_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Thư mục cache mô hình máy học (sentence-transformers / huggingface)
MODELS_CACHE_DIR = PROJECT_ROOT / "models_cache"

# ==============================================================================
# 3. MÔ HÌNH HỌC MÁY & LLM (MODEL DIRECTORIES)
# ==============================================================================

MODEL_DIR = CRAWLER_DIR / "model"
LLM_DIR = MODEL_DIR / "llm"
ML_DIR = MODEL_DIR / "ml"
ML_ARTIFACTS_DIR = ML_DIR / "artifacts"

# ==============================================================================
# 4. TẬP TIN DỮ LIỆU CHUẨN (STANDARD FILE PATHS)
# ==============================================================================

# SQLite Staging DB lưu trữ dữ liệu thô duy nhất
STAGING_DB_PATH = RAW_DATA_DIR / "staging.db"

# Checkpoint LLM (Ưu tiên JSONL tốc độ cao, tương thích ngược .json)
LLM_CHECKPOINT_PATH = PROCESSED_DATA_DIR / "checkpoint_reports.jsonl"
LEGACY_JSON_CHECKPOINT_PATH = PROCESSED_DATA_DIR / "checkpoint_reports.json"
LEGACY_LLM_CHECKPOINT_PATH = LLM_DIR / "checkpoint.json"
PROCESSED_PARQUET_PATH = PROCESSED_DATA_DIR / "listings_clean.parquet"

# Tập tin biến môi trường .env
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
CRAWLER_ENV_PATH = CRAWLER_DIR / ".env"

# ==============================================================================
# 5. CHUỖI ĐƯỜNG DẪN DẠNG STRING (Hỗ trợ các hàm/thư viện yêu cầu kiểu str)
# ==============================================================================

PROJECT_ROOT_STR = str(PROJECT_ROOT)
CRAWLER_DIR_STR = str(CRAWLER_DIR)
STAGING_DB_PATH_STR = str(STAGING_DB_PATH)
LLM_CHECKPOINT_PATH_STR = str(LLM_CHECKPOINT_PATH)
MODELS_CACHE_DIR_STR = str(MODELS_CACHE_DIR)
