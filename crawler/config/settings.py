import os
import sys
from dotenv import load_dotenv
from crawler.config.paths import CRAWLER_ENV_PATH

# 1. Tự động chuẩn hóa console output UTF-8 trên Windows
def setup_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

setup_windows_encoding()

# 2. Đảm bảo đọc file .env từ thư mục crawler/ và thư mục gốc của dự án
if CRAWLER_ENV_PATH.exists():
    load_dotenv(CRAWLER_ENV_PATH)


# 3. Cấu hình cào dữ liệu Chợ Tốt (NhaTot Spider)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

DELAY_MIN = 2.0
DELAY_MAX = 5.0
TIMEOUT = 15

CHOTOT_API_URL = "https://gateway.chotot.com/v1/public/ad-listing"
CATEGORY_PHONGTRO = 1050
LIMIT_PER_PAGE = 50

# Mã Vùng (region_v2) Chợ Tốt
REGIONS = {
    "hcm": 13000,          # TP. Hồ Chí Minh
    "hanoi": 12000,        # Hà Nội
    "danang": 3017,        # Đà Nẵng
    "binhduong": 2011,     # Bình Dương
    "dongnai": 2015,       # Đồng Nai
    "cantho": 9047,        # Cần Thơ
}


# 4. Cấu hình CSDL PostgreSQL & SQLAlchemy
def get_database_url(override_url: str | None = None) -> str:
    url = override_url or os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    server = os.environ.get("POSTGRES_SERVER", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "smart_housing_db")
    return f"postgresql+psycopg2://{user}:{password}@{server}:{port}/{db}"


# 5. Cấu hình Gemini LLM & Dynamic Chunker
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS", "")
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
DEFAULT_MAX_TOKENS_PER_CHUNK = 2500
DEFAULT_MAX_ITEMS_PER_CHUNK = 5
DEFAULT_RPM_DELAY = 1.0
DEFAULT_MAX_RETRIES = 5


# 6. Cấu hình Vector Embedding
DEFAULT_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
DEFAULT_EMBED_BATCH_SIZE = 32
