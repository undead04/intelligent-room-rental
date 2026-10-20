import os
import json
import time
from abc import ABC, abstractmethod
from crawler.config.paths import RAW_DATA_DIR
from crawler.staging_db import staging_db

class BaseSpider(ABC):
    """
    Lớp cơ sở trừu tượng (Base Spider) cho các nguồn cào dữ liệu phòng trọ.
    Mọi nguồn dữ liệu mới (Chợ Tốt, Phongtro123, Batdongsan,...) đều kế thừa lớp này.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.raw_dir = str(RAW_DATA_DIR)
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.staging_db = staging_db

    def log(self, msg: str):
        """In log kèm tiền tố nguồn dữ liệu (ép flush ra terminal)"""
        print(f"[{self.name.upper()}] {msg}", flush=True)

    def get_processed_ids(self) -> set:
        """Lấy danh sách các listing ID đã lưu trong kho Staging SQLite của nguồn này."""
        return self.staging_db.get_processed_ids(self.name)

    def get_checkpoint_file(self, region: str = "all") -> str:
        """Tên file checkpoint theo từng nguồn và khu vực"""
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return str(RAW_DATA_DIR / f"checkpoint_{self.name}_{region}.json")

    def load_checkpoint(self, region: str = "all") -> int:
        """Đọc mốc offset đã lưu từ checkpoint"""
        ckpt_file = self.get_checkpoint_file(region)
        # Hỗ trợ backward compatibility với file checkpoint cũ checkpoint_{region}.json
        legacy_file = os.path.join(os.path.dirname(ckpt_file), f"checkpoint_{region}.json")
        target_file = ckpt_file if os.path.exists(ckpt_file) else (legacy_file if os.path.exists(legacy_file) else None)
        
        if target_file and os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_offset", 0)
            except Exception:
                return 0
        return 0

    def save_checkpoint(self, offset: int, region: str = "all"):
        """Ghi mốc offset vào file checkpoint"""
        ckpt_file = self.get_checkpoint_file(region)
        with open(ckpt_file, "w", encoding="utf-8") as f:
            json.dump({
                "source": self.name,
                "region": region,
                "last_offset": offset,
                "updated_at": time.time()
            }, f, indent=2)
        self.log(f"Đã lưu checkpoint {region.upper()}: offset {offset}")

    def save_listing(self, item: dict) -> str:
        """Lưu bản ghi listing vào SQLite Staging Database (crawler/data/raw/staging.db)."""
        self.staging_db.save_listing(item, source=self.name)
        return item.get("listing_id") or f"{self.name}_{item.get('list_id') or item.get('ad_id')}"

    @abstractmethod
    def crawl(self, pages: int = 5, mode: str = "resume", region: str = "all") -> int:
        """
        Logic cào dữ liệu từ nguồn web/API.
        Trả về: số lượng tin mới đã thu thập.
        """
        pass

    @abstractmethod
    def verify(self, limit: int = 100, delay: float = 1.0) -> dict:
        """
        Logic kiểm tra trạng thái các tin đã cào trong quá khứ xem còn active hay đã hết hạn.
        Trả về: dict thống kê {'checked': int, 'active': int, 'expired': int}
        """
        pass

    def run(self, mode: str = "resume", pages: int = 5, region: str = "all", limit: int = 100, auto_clean: bool = True):
        """Hàm thực thi chuẩn cho spider"""
        if mode == "verify":
            self.log(f"Bắt đầu chế độ KIỂM TRA TRẠNG THÁI (Verify) tối đa {limit} tin...")
            stats = self.verify(limit=limit)
            self.log(f"Kết quả Verify: {stats.get('active', 0)} tin còn sống, {stats.get('expired', 0)} tin đã hết hạn/ẩn.")
        else:
            self.log(f"Bắt đầu chế độ CÀO DỮ LIỆU (Mode: {mode.upper()}, Pages: {pages}, Region: {region.upper()})...")
            total = self.crawl(pages=pages, mode=mode, region=region)
            self.log(f"Crawl hoàn tất! Đã thu thập thêm {total} tin mới.")

        if auto_clean:
            from crawler.etl.pipeline import run_pipeline
            self.log("Tự động chạy pipeline tổng hợp dữ liệu (ETL)...")
            run_pipeline()
