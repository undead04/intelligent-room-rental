"""Script khởi chạy Backend FastAPI nhanh chóng và tiện lợi.
Cách chạy:
    python run.py
hoặc:
    python -m uvicorn app.main:app --reload --port 8000
"""

import os
import sys
from pathlib import Path

# Đảm bảo mã hóa UTF-8 cho stdout trên môi trường Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm thư mục backend vào sys.path để import app.* không bị lỗi ModuleNotFoundError
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Đổi current working directory về backend nếu chạy từ thư mục khác
os.chdir(BACKEND_DIR)

if __name__ == "__main__":
    import uvicorn
    from app.core.config import settings

    print("=" * 60)
    print(f"🚀 KHỞI CHẠY BACKEND: {settings.PROJECT_NAME}")
    print(f"📖 Swagger UI Docs : http://localhost:8000/docs")
    print(f"🔍 ReDoc           : http://localhost:8000/redoc")
    print(f"❤️  Health Check    : http://localhost:8000{settings.API_V1_STR}/health")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(BACKEND_DIR / "app")],
        log_level="info",
    )
