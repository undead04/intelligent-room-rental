"""Offline Batch Embedding Script for Room Listings.
Sử dụng mô hình intfloat/multilingual-e5-base để sinh vector embedding (768 chiều)
cho toàn bộ dữ liệu tin đăng phòng trọ đã làm sạch.

Đầu ra tương thích hoàn toàn với:
1. `backend/scripts/load_data.py` (listing_embeddings.npy + listing_embedding_mapping.parquet)
2. Nạp trực tiếp vào PostgreSQL (pgvector) bảng `listing_embeddings`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Tự động thêm thư mục gốc và backend vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.services.embedding import EmbeddingModel


def load_listings_from_file(file_path: Path) -> List[Dict[str, Any]]:
    """Đọc danh sách tin đăng từ JSON hoặc CSV."""
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    ext = file_path.suffix.lower()
    if ext == ".json":
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("results") or list(data.values())
        return []

    if ext == ".csv":
        import pandas as pd
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        return df.to_dict(orient="records")

    raise ValueError(f"Định dạng file không hỗ trợ: {ext}. Chỉ hỗ trợ .json hoặc .csv")


def prepare_embedding_text(item: Dict[str, Any]) -> str:
    """Lấy hoặc tự động sinh chuỗi embedding_text nếu chưa có."""
    text = item.get("embedding_text")
    if text and str(text).strip():
        return str(text).strip()

    # Fallback tự động tổng hợp nếu file thô chưa qua bước transform
    from crawler.etl.enricher import build_enriched_embedding_text, extract_room_data_from_record
    report = item.get("report")
    extracted_data = extract_room_data_from_record(item, report)
    clean_desc = str(item.get("clean_description") or item.get("description") or "")
    clean_title = str(item.get("clean_title") or item.get("title") or "")
    desc = f"{clean_title}\n{clean_desc}".strip() if clean_title and clean_title not in clean_desc else clean_desc
    return build_enriched_embedding_text(extracted_data, clean_desc=desc, prefix="passage: ")


def run_offline_embedding(
    input_file: Path,
    output_dir: Path,
    model_name: str = "intfloat/multilingual-e5-base",
    batch_size: int = 32,
    device: Optional[str] = None,
    upsert_db: bool = False,
    limit: Optional[int] = None,
) -> tuple[int, int]:
    """Chạy toàn bộ quy trình Offline Embedding:
    1. Đọc dữ liệu phòng đã làm sạch.
    2. Chuẩn bị chuỗi văn bản với tiền tố 'passage: '.
    3. Sinh vector embedding hàng loạt theo batch.
    4. Lưu ra listing_embeddings.npy + listing_embedding_mapping.parquet.
    5. (Tùy chọn) Nạp trực tiếp vào PostgreSQL / pgvector.
    """
    print("\n" + "=" * 60)
    print(f"   KHỞI ĐỘNG OFFLINE BATCH EMBEDDING")
    print(f"   Model: {model_name}")
    print(f"   Input: {input_file}")
    print(f"   Output dir: {output_dir}")
    print("=" * 60 + "\n")

    # 1. Đọc dữ liệu đầu vào
    items = load_listings_from_file(input_file)
    if limit and limit > 0:
        items = items[:limit]

    total_items = len(items)
    print(f"[EMBED] Đã nạp {total_items} bài đăng từ {input_file}")
    if total_items == 0:
        return 0, 0

    # 2. Thu thập ID và chuỗi văn bản
    listing_ids: List[str] = []
    texts_to_embed: List[str] = []

    for item in items:
        lid = str(item.get("listing_id") or item.get("id") or "").strip()
        if not lid:
            continue
        text = prepare_embedding_text(item)
        listing_ids.append(lid)
        texts_to_embed.append(text)

    valid_count = len(listing_ids)
    print(f"[EMBED] Chuẩn bị sinh vector cho {valid_count} bài đăng hợp lệ...")

    # 3. Khởi tạo mô hình Embedding
    embed_model = EmbeddingModel(
        model_name=model_name,
        batch_size=batch_size,
        device=device,
    )
    print(f"[EMBED] Model đã sẵn sàng trên thiết bị: {embed_model.device}")

    # 4. Tiến hành Batch Encoding
    start_time = time.time()
    vectors = embed_model.encode_passages(texts_to_embed)
    elapsed = time.time() - start_time
    speed = valid_count / elapsed if elapsed > 0 else 0

    print(f"\n[EMBED] Hoàn tất nhúng {valid_count} bài trong {elapsed:.2f}s (~{speed:.1f} bài/giây)")
    print(f"[EMBED] Kích thước ma trận vector: {vectors.shape} (dtype: {vectors.dtype})")

    # 5. Lưu ra các định dạng file phục vụ Backend
    output_dir.mkdir(parents=True, exist_ok=True)
    npy_path = output_dir / "listing_embeddings.npy"
    parquet_path = output_dir / "listing_embedding_mapping.parquet"

    # Lưu file .npy
    np.save(npy_path, vectors.astype("float32"))
    print(f"[EMBED] Đã lưu mảng vector vào: {npy_path}")

    # Lưu mapping parquet (listing_id)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_arrays([pa.array(listing_ids)], names=["listing_id"])
        pq.write_table(table, parquet_path)
        print(f"[EMBED] Đã lưu file mapping vào: {parquet_path}")
    except ImportError:
        import pandas as pd
        df = pd.DataFrame({"listing_id": listing_ids})
        df.to_parquet(parquet_path, index=False)
        print(f"[EMBED] Đã lưu file mapping qua pandas vào: {parquet_path}")

    # 6. Tùy chọn nạp trực tiếp vào CSDL PostgreSQL
    db_loaded = 0
    if upsert_db:
        from app.core.database import SessionLocal
        from app.models import ListingEmbedding, Listing

        print("\n[EMBED] Bắt đầu nạp trực tiếp vector vào bảng listing_embeddings trong PostgreSQL...")
        session = SessionLocal()
        try:
            for idx, (lid, vec) in enumerate(zip(listing_ids, vectors)):
                # Kiểm tra listing có tồn tại trong bảng listings không
                if session.get(Listing, lid) is None:
                    continue

                vec_list = vec.astype("float32").tolist()
                content_hash = hashlib.sha256(vec.tobytes()).hexdigest()

                emb = (
                    session.query(ListingEmbedding)
                    .filter(
                        ListingEmbedding.listing_id == lid,
                        ListingEmbedding.model_name == model_name,
                    )
                    .one_or_none()
                )

                if emb is None:
                    emb = ListingEmbedding(
                        listing_id=lid,
                        model_name=model_name,
                        dimension=int(vectors.shape[1]),
                        vector=vec_list,
                        content_hash=content_hash,
                    )
                    session.add(emb)
                else:
                    emb.dimension = int(vectors.shape[1])
                    emb.vector = vec_list
                    emb.content_hash = content_hash

                db_loaded += 1
                if db_loaded % 500 == 0:
                    session.commit()
                    print(f"  -> Đã nạp {db_loaded}/{valid_count} vector vào CSDL...")

            session.commit()
            print(f"[EMBED] Đã nạp thành công {db_loaded} vector vào CSDL PostgreSQL!")
        except Exception as e:
            session.rollback()
            print(f"[EMBED] Lỗi khi nạp CSDL: {e}")
        finally:
            session.close()

    return valid_count, db_loaded


def main():
    parser = argparse.ArgumentParser(description="Offline Batch Embedding Runner for multilingual-e5-base")
    default_input = PROJECT_ROOT / "backend" / "app" / "datas" / "datas.json"
    default_output = PROJECT_ROOT / "backend" / "app" / "datas"

    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help=f"Đường dẫn file dữ liệu sạch (.json hoặc .csv). Mặc định: {default_input}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help=f"Thư mục lưu file vector (.npy, .parquet). Mặc định: {default_output}",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=settings.EMBEDDING_MODEL_NAME,
        help=f"Tên mô hình HuggingFace. Mặc định: {settings.EMBEDDING_MODEL_NAME}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.EMBEDDING_BATCH_SIZE,
        help=f"Batch size khi encode. Mặc định: {settings.EMBEDDING_BATCH_SIZE}",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Thiết bị chạy model: 'cuda', 'cpu', 'mps' (mặc định: tự động chọn)",
    )
    parser.add_argument(
        "--upsert-db",
        action="store_true",
        help="Nạp trực tiếp vector vào CSDL PostgreSQL (bảng listing_embeddings)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số lượng tin để test nhanh (ví dụ: --limit 10)",
    )

    args = parser.parse_args()
    run_offline_embedding(
        input_file=args.input,
        output_dir=args.output_dir,
        model_name=args.model_name,
        batch_size=args.batch_size,
        device=args.device,
        upsert_db=args.upsert_db,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
