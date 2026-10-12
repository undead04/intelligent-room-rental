import os
from sentence_transformers import SentenceTransformer


class EmbeddingModel:

    def __init__(
        self,
        model_name: str,
        batch_size: int = 32,
        cache_dir: str = "./models_cache",
    ):
        self.model_name = model_name
        self.batch_size = batch_size

        # Tạo thư mục cache nếu chưa có
        os.makedirs(cache_dir, exist_ok=True)

        # Hugging Face tự kiểm tra:
        # - Đã tải vào cache_dir -> Load từ ổ cứng
        # - Chưa có -> Tải về cache_dir rồi load
        self.model = SentenceTransformer(
            model_name_or_path=model_name, cache_folder=cache_dir
        )

    def encode(self, texts):
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )