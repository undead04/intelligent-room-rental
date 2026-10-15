import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.embedding import EmbeddingModel
except ImportError:
    from backend.app.services.embedding import EmbeddingModel


class ListingEmbedder:
    """[EMBED STAGE]
    Chịu trách nhiệm sinh vector ngữ nghĩa hàng loạt (Batch Offline Embedding)
    cho các bài đăng phòng trọ đã làm sạch bằng mô hình intfloat/multilingual-e5-base.
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        batch_size: int = 32,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = EmbeddingModel(
            model_name=model_name,
            batch_size=batch_size,
            device=device,
        )

    def embed_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sinh vector embedding cho danh sách các bài đăng:
        - Sử dụng trường embedding_text (chuỗi 5 khối ngữ cảnh).
        - Đảm bảo tiền tố 'passage: ' theo chuẩn E5.
        - Gắn mảng vector (768 chiều), model_name và dimension vào từng record.
        """
        if not records:
            return []

        print(f"\n[EMBED] Bắt đầu sinh vector embedding cho {len(records)} bài đăng...", flush=True)
        texts_to_embed = []
        for r in records:
            text = r.get("embedding_text")
            if not text or not str(text).strip():
                # Fallback nếu record chưa có embedding_text
                from crawler.etl.enricher import build_enriched_embedding_text, extract_room_data_from_record
                extracted_data = extract_room_data_from_record(r, r.get("report"))
                clean_desc = str(r.get("clean_description") or r.get("description") or "")
                clean_title = str(r.get("clean_title") or r.get("title") or "")
                desc = f"{clean_title}\n{clean_desc}".strip() if clean_title and clean_title not in clean_desc else clean_desc
                text = build_enriched_embedding_text(extracted_data, clean_desc=desc, prefix="passage: ")
                r["embedding_text"] = text

            texts_to_embed.append(str(text))

        start = time.time()
        vectors = self.model.encode_passages(texts_to_embed)
        elapsed = time.time() - start
        speed = len(records) / elapsed if elapsed > 0 else 0

        print(f"[EMBED] Hoàn tất sinh vector cho {len(records)} bài trong {elapsed:.2f}s (~{speed:.1f} bài/giây).", flush=True)

        for r, vec in zip(records, vectors):
            vec_list = vec.astype("float32").tolist()
            r["vector"] = vec_list
            r["embedding_model"] = self.model_name
            r["embedding_dim"] = int(vectors.shape[1])

        return records


if __name__ == "__main__":
    embedder = ListingEmbedder()
    sample = [{
        "listing_id": "test_1",
        "embedding_text": "passage: Vị trí: Quận 10 | Giá: 3,000,000 VND/tháng | Tiện ích: máy lạnh, WC riêng"
    }]
    embedded = embedder.embed_records(sample)
    print("Vector length:", len(embedded[0]["vector"]))
