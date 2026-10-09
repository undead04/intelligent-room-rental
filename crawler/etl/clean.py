import os
import sys
import json
import csv
from collections import Counter

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'listings')
PROCESSED_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'listings_clean.csv')

def combine_and_clean():
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    
    if not os.path.exists(RAW_DIR):
        print("Chưa có dữ liệu thô.", flush=True)
        return
        
    seen_ids = set()
    records = []
    
    for fname in sorted(os.listdir(RAW_DIR)):
        if fname.endswith(".json"):
            file_path = os.path.join(RAW_DIR, fname)
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    listing_id = data.get("listing_id")
                    if listing_id and listing_id not in seen_ids:
                        seen_ids.add(listing_id)
                        
                        # Chuẩn hóa trường trạng thái hoạt động (nếu file cũ chưa có)
                        if "is_active" not in data:
                            data["is_active"] = True
                        if "status" not in data:
                            data["status"] = "active"
                        if "phone" not in data:
                            data["phone"] = ""
                            
                        # Chuyển mảng images thành chuỗi ghép bởi dấu pipe '|' để lưu CSV gọn gàng
                        if isinstance(data.get("images"), list):
                            data["images"] = "|".join(data["images"])
                            
                        records.append(data)
                except Exception as e:
                    print(f"Lỗi đọc file {fname}: {e}", flush=True)
                    
    if not records:
        print("Không có bản ghi nào để xử lý.", flush=True)
        return
        
    # Thu thập đầy đủ các cột dữ liệu
    fieldnames = list(records[0].keys())
    for r in records[1:]:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)
                
    # Ghi ra CSV với utf-8-sig (BOM) để Excel mở không lỗi font
    with open(PROCESSED_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        
    print(f"\n[ETL] Đã lưu {len(records)} bản ghi đã làm sạch vào {PROCESSED_FILE}", flush=True)
    
    # Thống kê trạng thái tin (Còn sống vs Đã hết hạn)
    active_count = sum(1 for r in records if r.get("is_active") is True or str(r.get("is_active")).lower() == "true")
    expired_count = len(records) - active_count
    print(f"\nThống kê trạng thái tin đăng:")
    print(f"  - Đang hoạt động (Active): {active_count} tin ({active_count / len(records) * 100:.1f}%)")
    print(f"  - Đã hết hạn/Bị xóa (Expired): {expired_count} tin ({expired_count / len(records) * 100:.1f}%)")

    # Thống kê theo nguồn dữ liệu (Source)
    sources = [r.get("source", "unknown") for r in records]
    if sources:
        counts = Counter(sources)
        print("\nThống kê theo nguồn dữ liệu:")
        for src, count in counts.items():
            print(f"  - {src}: {count} tin")

    # Thống kê số lượng theo Quận/Huyện
    districts = [r.get("district") for r in records if r.get("district")]
    if districts:
        counts = Counter(districts)
        print("\nThống kê số lượng theo Quận/Huyện (Top 10):", flush=True)
        for dist, count in counts.most_common(10):
            print(f"  - {dist}: {count}", flush=True)

if __name__ == "__main__":
    combine_and_clean()
