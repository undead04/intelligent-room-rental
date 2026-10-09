import os
import sys
import time
from crawler.spiders.base import BaseSpider

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class PhongTro123Spider(BaseSpider):
    """
    Spider thu thập dữ liệu từ PhongTro123 (phongtro123.com).
    Kế thừa từ BaseSpider, sẵn sàng mở rộng khi cần thêm nguồn phụ theo kế hoạch đồ án.
    """
    
    def __init__(self):
        super().__init__(name="phongtro123")

    def crawl(self, pages: int = 5, mode: str = "resume", region: str = "all") -> int:
        self.log(f"Khởi động cào dữ liệu từ PhongTro123 (Pages: {pages}, Region: {region})...")
        # Khung cào dữ liệu HTML tĩnh (requests + BeautifulSoup) cho phongtro123
        self.log("Nguồn PhongTro123 đã được tích hợp vào kiến trúc BaseSpider. Sẵn sàng cấu hình selectors.")
        return 0

    def verify(self, limit: int = 100, delay: float = 1.0) -> dict:
        self.log("Kiểm tra trạng thái tin đăng PhongTro123...")
        return {"checked": 0, "active": 0, "expired": 0}
