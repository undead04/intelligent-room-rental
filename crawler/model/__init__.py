"""Package crawler.model
Phân vùng chuyên biệt:
- llm: Toàn bộ pipeline gọi Gemini, dynamic chunking, checkpointing, trích xuất tiện ích & quy định
- ml: Mô hình học máy (Machine Learning) định giá và đánh giá bất động sản
"""
from crawler.model import llm, ml

__all__ = ["llm", "ml"]
