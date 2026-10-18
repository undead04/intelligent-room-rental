from dotenv import load_dotenv
import os
from pathlib import Path

# Đảm bảo đọc file .env từ thư mục crawler/ và thư mục gốc của dự án
_current_file = Path(__file__).resolve()
_crawler_env = _current_file.parents[1] / ".env"
_root_env = _current_file.parents[2] / ".env"

if _crawler_env.exists():
    load_dotenv(_crawler_env)
if _root_env.exists():
    load_dotenv(_root_env)
load_dotenv()

# Cấu hình crawler
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

DELAY_MIN = 2.0
DELAY_MAX = 5.0
TIMEOUT = 15

# Chotot API & LLM Config
CHOTOT_API_URL = "https://gateway.chotot.com/v1/public/ad-listing"
GEMINI_API_KEYS = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
GEMINI_API_KEY = GEMINI_API_KEYS
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
