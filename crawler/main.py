import sys
import argparse

# Tự động điều chỉnh encoding cho stdout trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from crawler.spiders.nhatot import NhaTotSpider
from crawler.spiders.phongtro123 import PhongTro123Spider
from crawler.etl.pipeline import run_pipeline

SPIDERS = {
    "nhatot": NhaTotSpider,
    "phongtro123": PhongTro123Spider,
}

def main():
    parser = argparse.ArgumentParser(
        description="Homigo Crawler & ETL Pipeline Runner"
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Số trang cần cào (mặc định: 5 trang ~ 250 tin)."
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["hcm", "hanoi", "danang", "binhduong", "dongnai", "cantho", "all"],
        help="Khu vực cào (mặc định: 'hcm')."
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="resume",
        choices=["resume", "update", "verify"],
        help="Chế độ: 'resume' (cào tiếp), 'update' (quét tin mới), 'verify' (kiểm tra tin cũ)."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Trọn gói từ A-Z: Cào + LLM + ML Price Score + Embedding E5 + Nạp DB (PostgreSQL)."
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Tắt ETL (chỉ cào thô và lưu vào staging.db)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Số tin cũ cần kiểm tra khi dùng --mode verify (mặc định: 50)."
    )
    parser.add_argument(
        "--source",
        type=str,
        default="nhatot",
        choices=["nhatot", "phongtro123", "all"],
        help="Nguồn dữ liệu (mặc định: 'nhatot')."
    )

    args = parser.parse_args()

    # Cấu hình tự động theo preset --full
    extract_llm = args.full
    eval_price = args.full   # <-- Kích hoạt Machine Learning PriceEvaluator tính price_score
    embed = args.full        # <-- Kích hoạt E5 Embedding

    if args.full:
        print("[PRESET --full] Kích hoạt toàn bộ Pipeline:")
        print("  1. Cào dữ liệu phòng trọ")
        print("  2. Bóc tách thuộc tính LLM (Gemini)")
        print("  3. Thẩm định giá Machine Learning (Price Score)")
        print("  4. Sinh vector ngữ nghĩa Embedding (E5)")
        print("  5. Nạp trực tiếp vào PostgreSQL (pgvector)")

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
        run_pipeline(
            destinations=["db"],
            unprocessed_only=True,
            embed=embed,
            extract_llm=extract_llm,
            eval_price=eval_price,
        )

if __name__ == "__main__":
    main()
