import os
import sys
import time
from typing import Any, Dict, List, Optional
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def resolve_model_cache_dir(custom_path: Optional[str] = None) -> str:
    """Tự động tìm kiếm thư mục model_cache/models_cache độc lập cho container Crawler."""
    if custom_path and os.path.isabs(custom_path) and os.path.exists(custom_path):
        return custom_path

    env_dir = os.environ.get("MODEL_CACHE_DIR") or os.environ.get("EMBEDDING_MODEL_CACHE_DIR")
    if env_dir and os.path.exists(env_dir):
        return os.path.abspath(env_dir)

    crawler_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidate_dirs = [
        os.path.join(crawler_root, "model_cache"),
        os.path.join(crawler_root, "models_cache"),
        os.path.join(PROJECT_ROOT, "model_cache"),
        os.path.join(PROJECT_ROOT, "models_cache"),
    ]
    for c in candidate_dirs:
        if os.path.isdir(c):
            return os.path.abspath(c)

    default_dir = os.path.join(PROJECT_ROOT, "models_cache")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


class EmbeddingModel:
    """Mô hình nhúng ngữ nghĩa độc lập thuộc module Crawler (Offline Batch & Query Encoding).
    Không phụ thuộc vào code của module Backend để sẵn sàng đóng gói Container riêng biệt.
    """

    DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-base"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        batch_size: int = 32,
        cache_dir: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.is_e5 = "e5" in model_name.lower()

        if device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device

        resolved_cache = resolve_model_cache_dir(cache_dir)
        self.cache_dir = resolved_cache

        model_loaded = False
        try:
            self.model = SentenceTransformer(
                model_name_or_path=model_name,
                cache_folder=resolved_cache,
                device=self.device,
                local_files_only=True,
            )
            model_loaded = True
        except Exception:
            pass

        if not model_loaded:
            print(f"[EMBED] Đang tải mô hình {model_name} về cache: {resolved_cache}...", flush=True)
            self.model = SentenceTransformer(
                model_name_or_path=model_name,
                cache_folder=resolved_cache,
                device=self.device,
                local_files_only=False,
            )
            print(f"[EMBED] Đã lưu mô hình vào: {resolved_cache}", flush=True)

    def _format_text(self, text: str, is_query: bool = False) -> str:
        if not self.is_e5:
            return text
        t = str(text).strip()
        if is_query:
            return t if t.lower().startswith("query:") else f"query: {t}"
        return t if t.lower().startswith("passage:") else f"passage: {t}"

    def encode_passages(self, passages: List[str]) -> np.ndarray:
        formatted = [self._format_text(p, is_query=False) for p in passages]
        return self.model.encode(
            formatted,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(formatted) > 20,
        )


class ListingEmbedder:
    """[EMBED STAGE]
    Chịu trách nhiệm sinh vector ngữ nghĩa hàng loạt (Batch Offline Embedding)
    cho các bài đăng phòng trọ đã làm sạch bằng mô hình intfloat/multilingual-e5-base.
    Hoàn toàn độc lập với module Backend.
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
