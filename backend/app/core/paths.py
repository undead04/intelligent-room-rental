"""Quản lý tập trung toàn bộ đường dẫn thư mục và tập tin trong module Backend & Toàn dự án.

Giúp chuẩn hóa và tái sử dụng, loại bỏ việc lặp lại mã nguồn tính toán đường dẫn tương đối.
"""

from pathlib import Path

# ==============================================================================
# 1. THƯ MỤC CỐT LÕI (CORE DIRECTORIES)
# ==============================================================================

# Thư mục backend/app: .../backend/app
APP_DIR = Path(__file__).resolve().parent.parent

# Thư mục module Backend: .../backend
BACKEND_DIR = APP_DIR.parent

# Thư mục gốc toàn bộ dự án: .../Đồ Án tốt nghiệp
PROJECT_ROOT = BACKEND_DIR.parent

# ==============================================================================
# 2. CACHE VÀ DỮ LIỆU DÙNG CHUNG (SHARED CACHE & DATA)
# ==============================================================================

# Thư mục cache mô hình máy học (sentence-transformers / huggingface) nằm ở root dự án
MODELS_CACHE_DIR = PROJECT_ROOT / "models_cache"

# ==============================================================================
# 3. TẬP TIN CẤU HÌNH (CONFIG FILES)
# ==============================================================================

ENV_FILE_PATH = BACKEND_DIR / ".env"
PROJECT_ENV_FILE_PATH = PROJECT_ROOT / ".env"

# ==============================================================================
# 4. CHUỖI ĐƯỜNG DẪN DẠNG STRING (Hỗ trợ các thư viện yêu cầu kiểu str)
# ==============================================================================

PROJECT_ROOT_STR = str(PROJECT_ROOT)
BACKEND_DIR_STR = str(BACKEND_DIR)
APP_DIR_STR = str(APP_DIR)
MODELS_CACHE_DIR_STR = str(MODELS_CACHE_DIR)
ENV_FILE_PATH_STR = str(ENV_FILE_PATH)
