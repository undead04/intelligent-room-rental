import os
import sys
import argparse

# Tự động điều chỉnh encoding cho stdout trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.spiders.nhatot import NhaTotSpider
from crawler.spiders.phongtro123 import PhongTro123Spider
from crawler.etl.clean import combine_and_clean

SPIDERS = {
    "nhatot": NhaTotSpider,
    "phongtro123": PhongTro123Spider,
}

def main():
    parser = argparse.ArgumentParser(
        description="Module Thu Thập Dữ Liệu Phòng Trọ Đa Nguồn (Multi-source Crawler & Verifier)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="nhatot",
        choices=["nhatot", "phongtro123", "all"],
        help="Nguồn dữ liệu muốn chạy: 'nhatot', 'phongtro123', hoặc 'all'."
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="resume",
        choices=["resume", "update", "verify"],
        help="Chế độ: 'resume' (cào tiếp từ checkpoint), 'update' (quét tin mới từ trang 1), 'verify' (kiểm tra tin cũ còn sống hay hết hạn)."
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Số trang tối đa muốn cào (áp dụng cho resume/update)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Số lượng tin cũ muốn kiểm tra trạng thái hết hạn (áp dụng cho verify)."
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "hcm", "hanoi", "danang", "binhduong", "dongnai", "cantho"],
        help="Vùng/Thành phố muốn cào."
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Tắt tự động chạy pipeline ETL làm sạch sau khi hoàn tất."
    )

    args = parser.parse_args()

    active_spiders = []
    if args.source == "all":
        active_spiders = [cls() for cls in SPIDERS.values()]
    else:
        active_spiders = [SPIDERS[args.source]()]

    for spider in active_spiders:
        spider.run(
            mode=args.mode,
            pages=args.pages,
            region=args.region,
            limit=args.limit,
            auto_clean=False # Chạy clean 1 lần duy nhất ở cuối
        )

    if not args.no_clean:
        print("\n>>> TỔNG HỢP VÀ LÀM SẠCH TOÀN BỘ DỮ LIỆU ĐA NGUỒN (ETL)...", flush=True)
        combine_and_clean()

if __name__ == "__main__":
    main()
