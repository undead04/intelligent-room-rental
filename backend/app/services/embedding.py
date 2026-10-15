import os
from typing import List, Optional, Union
import numpy as np
from sentence_transformers import SentenceTransformer
import torch


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
        cache_dir: str = "./models_cache",
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

        os.makedirs(cache_dir, exist_ok=True)
        self.model = SentenceTransformer(
            model_name_or_path=model_name,
            cache_folder=cache_dir,
            device=self.device,
        )

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