import os
from typing import List, Optional, Union
import numpy as np
from sentence_transformers import SentenceTransformer
import torch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def resolve_model_cache_dir(custom_path: Optional[str] = None) -> str:
    """Tự động tìm kiếm và đồng nhất thư mục model_cache/models_cache trên máy.
    Tránh trường hợp mỗi module hoặc terminal chạy từ thư mục khác nhau tạo ra folder riêng.
    """
    if custom_path and os.path.isabs(custom_path) and os.path.exists(custom_path):
        return custom_path

    env_dir = os.environ.get("MODEL_CACHE_DIR") or os.environ.get("EMBEDDING_MODEL_CACHE_DIR")
    if env_dir and os.path.exists(env_dir):
        return os.path.abspath(env_dir)

    # Ưu tiên các thư mục cache đã tồn tại theo thứ tự
    candidate_dirs = [
        os.path.join(PROJECT_ROOT, "model_cache"),
        os.path.join(PROJECT_ROOT, "models_cache"),
        os.path.join(PROJECT_ROOT, "backend", "model_cache"),
        os.path.join(PROJECT_ROOT, "backend", "models_cache"),
        os.path.join(PROJECT_ROOT, "crawler", "model_cache"),
        os.path.join(PROJECT_ROOT, "crawler", "models_cache"),
    ]
    for c in candidate_dirs:
        if os.path.isdir(c):
            return os.path.abspath(c)

    # Nếu chỉ định custom_path tương đối, gán về thư mục gốc dự án
    if custom_path:
        target = os.path.abspath(os.path.join(PROJECT_ROOT, custom_path.lstrip("./\\")))
        os.makedirs(target, exist_ok=True)
        return target

    default_dir = os.path.join(PROJECT_ROOT, "models_cache")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


class EmbeddingModel:
    """Mô hình nhúng ngữ nghĩa (Embedding Model).
    Hỗ trợ tối ưu cho họ mô hình intfloat/multilingual-e5-base với cơ chế tiền tố:
    - Tìm kiếm thời gian thực (Query): tự động thêm tiền tố 'query: '
    - Nhúng tài liệu/tin đăng phòng trọ (Passage/Document): tự động thêm tiền tố 'passage: '
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

        # Tự động phát hiện GPU/CPU nếu không chỉ định rõ
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

        # 1. Thử nạp Offline trước (local_files_only=True)
        # Giúp nạp tức thì trong < 1s và KHÔNG BAO GIỜ ping mạng lên Hugging Face Hub nếu đã có cache
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

        # 2. Nếu chưa có trong cache cục bộ thì mới tải từ HuggingFace Hub (chỉ 1 lần duy nhất)
        if not model_loaded:
            print(f"[EmbeddingModel] Đang tải mô hình {model_name} về cache tập trung: {resolved_cache}...", flush=True)
            self.model = SentenceTransformer(
                model_name_or_path=model_name,
                cache_folder=resolved_cache,
                device=self.device,
                local_files_only=False,
            )
            print(f"[EmbeddingModel] Đã hoàn tất lưu mô hình vào: {resolved_cache}", flush=True)

    def _format_text(self, text: str, is_query: bool = False) -> str:
        """Định dạng tiền tố chuẩn cho mô hình E5."""
        if not self.is_e5:
            return text
        t = str(text).strip()
        if is_query:
            if not t.lower().startswith("query:"):
                return f"query: {t}"
        else:
            if not t.lower().startswith("passage:"):
                return f"passage: {t}"
        return t

    def encode_query(self, query: str) -> np.ndarray:
        """Tạo vector embedding cho 1 câu truy vấn người dùng (online search).
        Tự động thêm tiền tố 'query: ' cho mô hình E5.
        
        Returns:
            np.ndarray: Vector 1D (768 chiều).
        """
        formatted = self._format_text(query, is_query=True)
        return self.model.encode(
            formatted,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        """Tạo vector embedding cho danh sách câu truy vấn."""
        formatted = [self._format_text(q, is_query=True) for q in queries]
        return self.model.encode(
            formatted,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(formatted) > 50,
        )

    def encode_passage(self, passage: str) -> np.ndarray:
        """Tạo vector embedding cho 1 bài đăng phòng trọ.
        Tự động thêm tiền tố 'passage: ' cho mô hình E5.
        
        Returns:
            np.ndarray: Vector 1D (768 chiều).
        """
        formatted = self._format_text(passage, is_query=False)
        return self.model.encode(
            formatted,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    def encode_passages(self, passages: List[str]) -> np.ndarray:
        """Tạo vector embedding hàng loạt cho bài đăng phòng trọ (batch offline).
        
        Returns:
            np.ndarray: Ma trận 2D (N, 768).
        """
        formatted = [self._format_text(p, is_query=False) for p in passages]
        return self.model.encode(
            formatted,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(formatted) > 50,
        )

    def encode(
        self,
        texts: Union[str, List[str]],
        is_query: bool = False,
        normalize_embeddings: bool = True,
    ) -> np.ndarray:
        """Hàm encode tổng quát (tương thích ngược hoàn toàn với code cũ)."""
        if isinstance(texts, str):
            return self.encode_query(texts) if is_query else self.encode_passage(texts)
        return self.encode_queries(texts) if is_query else self.encode_passages(texts)