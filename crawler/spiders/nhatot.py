import os
import sys
import json
import time
import random
import traceback
import argparse

# Tự động thêm thư mục gốc dự án vào sys.path để hỗ trợ import module 'crawler' khi chạy trực tiếp từ bất kỳ thư mục nào
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.config import settings
from crawler.utils.http import fetch_with_retry
from crawler.utils.parser import parse_chotot_item
from crawler.etl.clean import combine_and_clean

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'listings')
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'checkpoint.json')

def init_dirs():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)

def get_processed_ids():
    processed = set()
    if os.path.exists(RAW_DIR):
        for fname in os.listdir(RAW_DIR):
            if fname.endswith(".json"):
                pid = fname.replace("nhatot_", "").replace(".json", "")
                processed.add(pid)
    return processed

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_offset", 0)
        except:
            return 0
    return 0

def save_checkpoint(offset):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_offset": offset, "updated_at": time.time()}, f)
    print(f"[Checkpoint] Đã lưu mốc offset: {offset}")

def run_spider(max_pages=5, mode="resume", region="all", auto_clean=True):
    init_dirs()
    processed_ids = get_processed_ids()
    print(f"Đã có {len(processed_ids)} tin đăng trong kho dữ liệu thô.")
    
    # Xác định mã vùng (region_v2)
    region_code = None
    if region in settings.REGIONS:
        region_code = settings.REGIONS[region]
        print(f"Đã chọn vùng: {region.upper()} (Code: {region_code})")
    elif region == "all":
        print("Đã chọn vùng: TOÀN QUỐC (Tất cả tỉnh thành)")
    else:
        print(f"Cảnh báo: Vùng '{region}' không có trong cấu hình, mặc định cào TOÀN QUỐC.")

    if mode == "update":
        offset = 0
        print(">>> CHẠY CHẾ ĐỘ UPDATE: Bắt đầu quét từ Trang 1 (Tìm tin mới).")
    else:
        offset = load_checkpoint()
        if offset > 0:
            print(f">>> CHẠY CHẾ ĐỘ RESUME: Tiếp tục cào dữ liệu lịch sử từ offset {offset}.")
        else:
            print(">>> CHẠY CHẾ ĐỘ RESUME: Bắt đầu từ offset 0 (Chưa có checkpoint).")
            
    total_crawled = 0
    page = offset // settings.LIMIT_PER_PAGE
    target_page = page + max_pages
    
    try:
        while page < target_page:
            print(f"\n--- Crawling page {page + 1}, offset {offset} ---")
            params = {
                "limit": settings.LIMIT_PER_PAGE,
                "o": offset,
                "cg": settings.CATEGORY_PHONGTRO
            }
            if region_code:
                params["region_v2"] = region_code
            
            data = fetch_with_retry(settings.CHOTOT_API_URL, params=params)
            if not data or 'ads' not in data:
                print("Không lấy được dữ liệu hoặc hết dữ liệu. Dừng lại.")
                break
                
            ads = data['ads']
            if not ads:
                print("Không còn tin đăng nào.")
                break
                
            new_in_page = 0
            for ad in ads:
                ad_id = str(ad.get('list_id') or ad.get('ad_id'))
                if not ad_id:
                    continue
                    
                if ad_id in processed_ids:
                    continue
                    
                parsed_item = parse_chotot_item(ad)
                
                # Lưu ra file JSON
                file_path = os.path.join(RAW_DIR, f"nhatot_{ad_id}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_item, f, ensure_ascii=False, indent=2)
                    
                processed_ids.add(ad_id)
                new_in_page += 1
                total_crawled += 1
                
            print(f"Trang {page + 1}: Lấy thành công {new_in_page} tin MỚI (tổng: {len(ads)} tin).")
            
            # Logic dừng sớm cho chế độ update
            if mode == "update" and new_in_page == 0:
                print(">>> Đã gặp một trang toàn bộ là tin cũ. TỰ ĐỘNG DỪNG CẬP NHẬT để tiết kiệm tài nguyên!")
                break
            
            offset += settings.LIMIT_PER_PAGE
            page += 1
            
            # Chỉ lưu checkpoint ở chế độ resume (cào sâu). Chế độ update không lưu đè checkpoint.
            if mode == "resume":
                save_checkpoint(offset)
            
            # Delay tránh rate limit
            delay = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
            print(f"Nghỉ {delay:.2f}s...")
            time.sleep(delay)
            
    except KeyboardInterrupt:
        print("\n[Ngắt] Bạn vừa nhấn dừng chương trình (Ctrl+C).")
        if mode == "resume":
            save_checkpoint(offset)
    except Exception as e:
        print(f"\n[Lỗi nghiêm trọng] Đã xảy ra lỗi: {e}")
        traceback.print_exc()
        if mode == "resume":
            save_checkpoint(offset)
        
    print(f"\nCrawling hoàn tất! Lấy mới được {total_crawled} tin đăng.")
    
    # Tự động gọi ETL clean data khi cào xong
    if auto_clean:
        print("\n>>> TỰ ĐỘNG TỔNG HỢP VÀ LÀM SẠCH DỮ LIỆU (ETL)...")
        combine_and_clean()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chợ Tốt Multi-Region Crawler")
    parser.add_argument(
        "--mode", 
        type=str, 
        choices=["resume", "update"], 
        default="resume",
        help="Chế độ chạy: 'resume' (cào tiếp từ checkpoint) hoặc 'update' (quét tin mới từ trang 1)."
    )
    parser.add_argument(
        "--pages", 
        type=int, 
        default=5,
        help="Số trang tối đa muốn crawl."
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
    run_spider(max_pages=args.pages, mode=args.mode, region=args.region, auto_clean=not args.no_clean)
