import os
import sys
import argparse
from pathlib import Path

# Đảm bảo root dự án có trong sys.path khi chạy file độc lập
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from crawler.config.settings import GEMINI_API_KEYS, setup_windows_encoding
setup_windows_encoding()

from crawler.config.paths import (
    LLM_CHECKPOINT_PATH,
    LEGACY_JSON_CHECKPOINT_PATH,
    LEGACY_LLM_CHECKPOINT_PATH,
)
from crawler.etl.extract import extract_raw_listings
from crawler.etl.transform import ListingTransformer
from crawler.etl.load import DataLoader
from crawler.staging_db import staging_db
from crawler.model.llm.pipeline import run_pipeline_chunking

def run_pipeline(
    destinations: list[str] = None,
    active_only: bool = False,
    unprocessed_only: bool = False,
    embed: bool = False,
    extract_llm: bool = False,
    checkpoint_path: str = None,
    eval_price: bool = False,
    limit: int = None,
) -> list[dict]:
    """
    Điều phối luồng ETL toàn diện:
    1. EXTRACT: Đọc dữ liệu từ SQLite Staging DB (hỗ trợ incremental)
    2. LLM EXTRACT: (Tùy chọn --extract-llm) Bóc tách ngữ nghĩa & kiểm định bằng chứng qua Gemini LLM
    3. TRANSFORM: Làm sạch, khử trùng lặp, chuẩn hóa kiểu, tích hợp LLM báo cáo & embedding_text
    4. EVAL PRICE: (Tùy chọn --eval-price) Thẩm định giá thị trường & chấm điểm price_score
    5. EMBED: Sinh vector offline với intfloat/multilingual-e5-base
    6. LOAD: Nạp trực tiếp vào cơ sở dữ liệu PostgreSQL (pgvector)
    7. MARK: Đánh dấu is_processed = 1 trong Staging DB
    
    Returns:
        list[dict]: Danh sách các bản ghi đã làm sạch.
    """
    if destinations is None:
        destinations = ["db"]
    print("\n" + "#" * 60, flush=True)
    print("     KHỞI ĐỘNG PIPELINE ETL (EXTRACT - TRANSFORM - LOAD)", flush=True)
    print("#" * 60 + "\n", flush=True)

    # 1. EXTRACT
    raw_records = extract_raw_listings(
        unprocessed_only=unprocessed_only,
        limit=limit,
    )
    if not raw_records:
        print("[ETL] Không có dữ liệu thô để xử lý. Dừng pipeline.", flush=True)
        return []

    # 1.5. LLM EXTRACTION (Chạy bóc tách ngữ nghĩa qua Gemini nếu được yêu cầu)
    if extract_llm:
        raw_keys = GEMINI_API_KEYS or ""
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        if keys:
            print(f"[ETL] Đang kích hoạt LLM Gemini bóc tách ngữ nghĩa cho {len(raw_records)} bài...", flush=True)
            ckpt_p = Path(checkpoint_path) if checkpoint_path else LLM_CHECKPOINT_PATH
            llm_results, _ = run_pipeline_chunking(
                datas=raw_records,
                api_keys=keys,
                checkpoint_path=ckpt_p,
            )
            checkpoint_path = str(ckpt_p)
        else:
            print("[ETL] Cảnh báo: --extract-llm được bật nhưng chưa cấu hình GEMINI_API_KEYS trong file .env. Bỏ qua bước LLM.", flush=True)

    # Tự động tìm checkpoint có sẵn nếu chưa chỉ định checkpoint_path
    if not checkpoint_path:
        default_ckpts = [
            str(LLM_CHECKPOINT_PATH),
            str(LEGACY_JSON_CHECKPOINT_PATH),
            str(LEGACY_LLM_CHECKPOINT_PATH),
        ]
        for p in default_ckpts:
            if os.path.exists(p):
                checkpoint_path = p
                print(f"[ETL] Tự động phát hiện và áp dụng báo cáo trích xuất LLM từ: {p}", flush=True)
                break

    # 2. TRANSFORM
    transformer = ListingTransformer(llm_reports=checkpoint_path, enable_price_evaluator=eval_price)
    cleaned_records = transformer.transform(raw_records, active_only=active_only)
    if not cleaned_records:
        print("[ETL] Không có dữ liệu hợp lệ sau khi Transform. Dừng pipeline.", flush=True)
        return []

    # 3. EMBED (Sinh vector ngữ nghĩa bằng multilingual-e5-base)
    if embed :
        from crawler.etl.embed import ListingEmbedder
        embedder = ListingEmbedder()
        cleaned_records = embedder.embed_records(cleaned_records)

    # 4. LOAD (Chỉ nạp trực tiếp vào PostgreSQL, không tạo file parquet hay csv)
    loader = DataLoader()
    try:
        loader.load_to_postgres(cleaned_records)
    except Exception as e:
        print(f"[LOAD] Bỏ qua nạp PostgreSQL (lỗi kết nối hoặc DB chưa bật): {e}", flush=True)

    # 5. MARK PROCESSED IN STAGING DB
    processed_ids = [r.get("listing_id") for r in cleaned_records if r.get("listing_id")]
    if processed_ids:
        updated = staging_db.mark_as_processed(processed_ids)
        print(f"[ETL] Đã cập nhật trạng thái is_processed = 1 cho {updated} tin trong Staging DB.", flush=True)

    # Báo cáo thống kê
    loader.print_summary(cleaned_records)
    return cleaned_records

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Homigo ETL Pipeline Runner (Chạy độc lập để Debug)")

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số bản ghi xử lý (rất tiện để debug nhanh vài bài)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Xử lý toàn bộ dữ liệu trong Staging DB (mặc định chỉ xử lý tin mới chưa qua ETL)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Bật bóc tách tiện ích/an ninh bằng Gemini LLM",
    )
    parser.add_argument(
        "--price",
        action="store_true",
        help="Bật Machine Learning PriceEvaluator tính price_score",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Bật E5 sinh vector embedding",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Bật trọn gói: LLM + ML Price Score + E5 Embedding + Nạp DB",
    )
    parser.add_argument(
        "--dest",
        nargs="+",
        default=["db"],
        choices=["db", "postgres"],
        help="Đích đến để lưu dữ liệu (mặc định: 'db')",
    )

    args = parser.parse_args()

    extract_llm = args.full or args.llm
    eval_price = args.full or args.price
    embed = args.full or args.embed

    run_pipeline(
        destinations=args.dest,
        unprocessed_only=not args.all,
        embed=embed,
        extract_llm=extract_llm,
        eval_price=eval_price,
        limit=args.limit,
    )

