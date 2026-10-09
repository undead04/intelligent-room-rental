import os
import sys
import json

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_RAW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "listings"))

def extract_raw_listings(raw_dir: str = None) -> list[dict]:
    """
    [EXTRACT STAGE]
    Đọc toàn bộ các file JSON thô trong thư mục data/raw/listings/.
    Hỗ trợ đọc từ nhiều nguồn khác nhau (nhatot, phongtro123,...).
    
    Returns:
        list[dict]: Danh sách các bản ghi JSON thô chưa qua làm sạch.
    """
    target_dir = raw_dir or DEFAULT_RAW_DIR
    if not os.path.exists(target_dir):
        print(f"[EXTRACT] Thư mục dữ liệu thô không tồn tại: {target_dir}", flush=True)
        return []

    raw_records = []
    error_count = 0

    files = sorted([f for f in os.listdir(target_dir) if f.endswith(".json")])
    print(f"[EXTRACT] Bắt đầu đọc {len(files)} file dữ liệu thô từ: {target_dir}", flush=True)

    for fname in files:
        fpath = os.path.join(target_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    raw_records.append(data)
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"[EXTRACT] Lỗi đọc file {fname}: {e}", flush=True)

    if error_count > 5:
        print(f"[EXTRACT] ... và thêm {error_count - 5} file khác bị lỗi đọc.", flush=True)

    print(f"[EXTRACT] Hoàn tất! Đã trích xuất thành công {len(raw_records)} bản ghi.", flush=True)
    return raw_records

if __name__ == "__main__":
    records = extract_raw_listings()
    print(f"Tổng số bản ghi trích xuất: {len(records)}")
