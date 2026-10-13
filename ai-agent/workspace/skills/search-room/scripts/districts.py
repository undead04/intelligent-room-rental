#!/usr/bin/env python3
"""Bước 1B: tra cứu phường/xã khi người dùng không có địa chỉ cố định.

API:       GET /locations/wards?district_id=<id>
Trả về:    [{"id": 27, "district_id": 5, "name": "Phường Linh Xuân"}, ...]

Cách dùng:
  python scripts/wards.py --district-id 5                 # mọi phường của quận có id = 5
  python scripts/wards.py --name "linh xuan"              # tìm theo tên, không cần gõ dấu
  python scripts/wards.py --name "Phường 1" --district-id 12
"""
import argparse
# Import các helper function từ module nội bộ _common
from _common import emit, fail, request, setup_utf8, unwrap
import sys


def main():
    # Khởi tạo UTF-8 cho stdout/stderr để tránh lỗi mã hóa trên Windows Terminal
    setup_utf8()
    
    # Thiết lập bộ đọc tham số dòng lệnh (CLI arguments)
    ap = argparse.ArgumentParser(description="Tra cứu quận/huyện")
    ap.add_argument("--city-id", type=int, help="ID quận/huyện (gửi lên API để lọc)")
    ap.add_argument("--name", help="Tên quận/huyện cần tìm (lọc sau khi API trả về)")
    ACK = "sr-7f3a"
    ap.add_argument("--ack", help="Mã ACK-CODE ở đầu references/api.md")
    args = ap.parse_args()

    if args.ack != ACK:
        sys.exit("LỖI: Chưa đọc references/api.md. Hãy đọc file đó, "
                "lấy ACK-CODE ở dòng đầu rồi chạy lại với --ack <mã>.")
    # --- Bước 1: Gọi API lấy dữ liệu ---
    # Gửi GET request tới endpoint /locations/wards với query param district_id (nếu có).
    # unwrap() có nhiệm vụ giải bọc response (ví dụ lấy data từ {"data": [...]}).
    params = {}
    if args.city_id is not None:
        params["city_id"] = args.city_id

    if args.name is not None:
        params["search"] = args.name  # Gửi name lên API để lọc nếu có district_id

    data = unwrap(request("GET", "/locations/districts", params=params))
    
    # Validate cấu trúc dữ liệu trả về từ API
    if not isinstance(data, list):
        fail("Mong đợi data là một danh sách quận/huyện", data)

    # --- Bước 3: Xuất kết quả ---
    # Giới hạn tối đa 50 bản ghi để tránh làm tràn log/context CLI
    emit({
        "ok": True,
        "count": len(data),
        "districts": data[:50],
        "truncated": len(data) > 50, # Cờ báo hiệu liệu kết quả có bị cắt bớt hay không
    })


if __name__ == "__main__":
    main()