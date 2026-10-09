import os
import sys
import json
import time
import random
import traceback
import argparse
from datetime import datetime

# Tự động điều chỉnh encoding cho stdout trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.config import settings
from crawler.utils.http import fetch_with_retry, fetch_with_status
from crawler.utils.parser import parse_chotot_item
from crawler.spiders.base import BaseSpider

class NhaTotSpider(BaseSpider):
    """Spider thu thập và kiểm tra trạng thái tin đăng từ Chợ Tốt / Nhà Tốt (nhatot.com)"""
    
    def __init__(self):
        super().__init__(name="nhatot")

    def crawl(self, pages: int = 5, mode: str = "resume", region: str = "all") -> int:
        processed_ids = self.get_processed_ids()
        self.log(f"Đã có {len(processed_ids)} tin đăng trong kho dữ liệu thô.")
        
        region_code = None
        if region in settings.REGIONS:
            region_code = settings.REGIONS[region]
            self.log(f"Đã chọn vùng: {region.upper()} (Code: {region_code})")
        elif region == "all":
            self.log("Đã chọn vùng: TOÀN QUỐC (Tất cả tỉnh thành)")
        else:
            self.log(f"Cảnh báo: Vùng '{region}' không có trong cấu hình, mặc định cào TOÀN QUỐC.")

        if mode == "update":
            offset = 0
            self.log(">>> CHẠY CHẾ ĐỘ UPDATE: Bắt đầu quét từ Trang 1 (Tìm tin mới).")
        else:
            offset = self.load_checkpoint(region)
            if offset > 0:
                self.log(f">>> CHẠY CHẾ ĐỘ RESUME ({region.upper()}): Tiếp tục cào từ offset {offset}.")
            else:
                self.log(f">>> CHẠY CHẾ ĐỘ RESUME ({region.upper()}): Bắt đầu từ offset 0.")

        total_crawled = 0
        page = offset // settings.LIMIT_PER_PAGE
        target_page = page + pages

        try:
            while page < target_page:
                self.log(f"\n--- Crawling page {page + 1}, offset {offset} ---")
                params = {
                    "limit": settings.LIMIT_PER_PAGE,
                    "o": offset,
                    "cg": settings.CATEGORY_PHONGTRO
                }
                if region_code:
                    params["region_v2"] = region_code

                data = fetch_with_retry(settings.CHOTOT_API_URL, params=params)
                if not data or 'ads' not in data:
                    self.log("Không lấy được dữ liệu hoặc hết dữ liệu. Dừng lại.")
                    break

                ads = data['ads']
                if not ads:
                    self.log("Không còn tin đăng nào.")
                    break

                new_in_page = 0
                for ad in ads:
                    ad_id = str(ad.get('list_id') or ad.get('ad_id'))
                    if not ad_id:
                        continue

                    if ad_id in processed_ids:
                        continue

                    parsed_item = parse_chotot_item(ad)
                    self.save_listing(parsed_item)

                    processed_ids.add(ad_id)
                    new_in_page += 1
                    total_crawled += 1

                self.log(f"Trang {page + 1}: Lấy thành công {new_in_page} tin MỚI (tổng: {len(ads)} tin).")

                if mode == "update" and new_in_page == 0:
                    self.log(">>> Đã gặp một trang toàn bộ là tin cũ. TỰ ĐỘNG DỪNG CẬP NHẬT để tiết kiệm tài nguyên!")
                    break

                offset += settings.LIMIT_PER_PAGE
                page += 1

                if mode == "resume":
                    self.save_checkpoint(offset, region)

                delay = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
                self.log(f"Nghỉ {delay:.2f}s...")
                time.sleep(delay)

        except KeyboardInterrupt:
            self.log("\n[Ngắt] Bạn vừa nhấn dừng chương trình (Ctrl+C).")
            if mode == "resume":
                self.save_checkpoint(offset, region)
        except Exception as e:
            self.log(f"\n[Lỗi nghiêm trọng] Đã xảy ra lỗi: {e}")
            traceback.print_exc()
            if mode == "resume":
                self.save_checkpoint(offset, region)

        return total_crawled

    def verify(self, limit: int = 100, delay: float = 1.0) -> dict:
        """
        Kiểm tra danh sách tin đã lưu trên Chợ Tốt:
        - Gọi endpoint chi tiết: https://gateway.chotot.com/v1/public/ad-listing/{list_id}
        - Nếu 404 hoặc status != active: đánh dấu is_active = False, status = 'expired'
        - Nếu 200 và status == active: đánh dấu is_active = True
        - Cập nhật trường last_checked_at vào file JSON
        """
        stats = {"checked": 0, "active": 0, "expired": 0, "error": 0}
        
        # Tìm các file của nhatot
        files_to_check = []
        for fname in os.listdir(self.raw_dir):
            if fname.startswith("nhatot_") and fname.endswith(".json"):
                fpath = os.path.join(self.raw_dir, fname)
                files_to_check.append(fpath)

        if not files_to_check:
            self.log("Không có file dữ liệu nào để kiểm tra.")
            return stats

        # Đọc metadata sơ bộ để ưu tiên kiểm tra các tin cũ nhất hoặc chưa từng verify
        indexed = []
        for fp in files_to_check:
            try:
                # Đọc nhanh file để lấy list_id và last_checked_at
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    last_checked = data.get("last_checked_at") or data.get("crawled_at") or "1970-01-01"
                    is_active = data.get("is_active", True)
                    list_id = data.get("list_id") or data.get("ad_id")
                    indexed.append({
                        "file_path": fp,
                        "list_id": str(list_id),
                        "last_checked": last_checked,
                        "is_active": is_active,
                        "data": data
                    })
            except Exception:
                continue

        # Ưu tiên các tin đang active và được kiểm tra lâu nhất
        indexed.sort(key=lambda x: (not x["is_active"], x["last_checked"]))

        target_list = indexed[:limit] if limit > 0 else indexed
        self.log(f"Bắt đầu kiểm tra {len(target_list)} tin cũ (Tổng kho: {len(indexed)} tin)...")

        for idx, item_info in enumerate(target_list, 1):
            list_id = item_info["list_id"]
            fp = item_info["file_path"]
            item_data = item_info["data"]

            detail_url = f"https://gateway.chotot.com/v1/public/ad-listing/{list_id}"
            status_code, resp_data = fetch_with_status(detail_url)

            now_iso = datetime.now().isoformat()
            item_data["last_checked_at"] = now_iso

            if status_code == 404:
                item_data["is_active"] = False
                item_data["status"] = "expired_or_deleted"
                stats["expired"] += 1
                self.log(f"[{idx}/{len(target_list)}] Tin {list_id}: ĐÃ HẾT HẠN (HTTP 404)")
            elif status_code == 200 and resp_data:
                ad = resp_data.get("ad", {})
                ad_status = ad.get("status")
                ad_state = ad.get("state")

                if ad_status == "active" and ad_state == "accepted":
                    item_data["is_active"] = True
                    item_data["status"] = "active"
                    stats["active"] += 1
                    # Lưu thêm số điện thoại nếu có
                    if ad.get("phone") and not item_data.get("phone"):
                        item_data["phone"] = ad.get("phone")
                    self.log(f"[{idx}/{len(target_list)}] Tin {list_id}: CÒN HOẠT ĐỘNG (Active)")
                else:
                    item_data["is_active"] = False
                    item_data["status"] = ad_status or "inactive"
                    stats["expired"] += 1
                    self.log(f"[{idx}/{len(target_list)}] Tin {list_id}: ĐÃ ẨN/HẾT HẠN (Status: {ad_status})")
            else:
                stats["error"] += 1
                self.log(f"[{idx}/{len(target_list)}] Tin {list_id}: Lỗi kiểm tra (HTTP {status_code})")

            # Ghi lại file json đã cập nhật trạng thái
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(item_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.log(f"Lỗi ghi file {fp}: {e}")

            stats["checked"] += 1
            time.sleep(random.uniform(delay * 0.8, delay * 1.2))

        return stats

def run_spider(max_pages=5, mode="resume", region="all", auto_clean=True, limit=100):
    """Hàm chạy tương thích ngược"""
    spider = NhaTotSpider()
    spider.run(mode=mode, pages=max_pages, region=region, limit=limit, auto_clean=auto_clean)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chợ Tốt Multi-Region & Verification Crawler")
    parser.add_argument(
        "--mode", 
        type=str, 
        choices=["resume", "update", "verify"], 
        default="resume",
        help="Chế độ: 'resume' (cào tiếp từ checkpoint), 'update' (quét tin mới từ trang 1), 'verify' (kiểm tra tin cũ còn sống hay hết hạn)."
    )
    parser.add_argument(
        "--pages", 
        type=int, 
        default=5,
        help="Số trang tối đa muốn crawl (dùng cho resume/update)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Số lượng tin cũ muốn kiểm tra trạng thái (dùng cho verify)."
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "hcm", "hanoi", "danang", "binhduong", "dongnai", "cantho"],
        help="Vùng/Thành phố muốn cào: 'all' (Toàn quốc), 'hcm', 'hanoi', 'danang', 'binhduong', 'dongnai', 'cantho'."
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Tắt tự động chạy ETL clean data sau khi cào."
    )
    
    args = parser.parse_args()
    run_spider(
        max_pages=args.pages, 
        mode=args.mode, 
        region=args.region, 
        auto_clean=not args.no_clean,
        limit=args.limit
    )
