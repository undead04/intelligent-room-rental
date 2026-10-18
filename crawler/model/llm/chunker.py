import os
import sys
from typing import Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.utils.count_token import get_token_count



def create_dynamic_chunks(
    articles: List[Dict[str, str]],
    max_tokens_per_chunk: int = 2500,  # Ngưỡng an toàn tối ưu cho Task Extractor
    max_items_per_chunk: int = 5,      # Giới hạn tối ưu 5 bài/chunk để LLM trích xuất đầy đủ chi tiết mọi tiện ích, tránh attention degradation
    model_name: str = "gpt-4o",
) -> List[List[Dict[str, str]]]:
    """
    Gom các bài đăng vào chunk sao cho tổng token không vượt quá max_tokens_per_chunk
    và số bài trong chunk không vượt quá max_items_per_chunk (tránh tràn output tokens của LLM).
    """
    chunks: List[List[Dict[str, str]]] = []
    current_chunk: List[Dict[str, str]] = []
    current_tokens = 0

    for article in articles:
        art_id = str(article.get("listing_id") or article.get("id", ""))
        content = (
            article.get("text")
            or article.get("description")
            or article.get("title")
            or ""
        )
        article_text = f"ID: {art_id}\nText: {content}"
        article_tokens = get_token_count(article_text, model_name)

        # EDGE CASE: Nếu 1 bài đơn lẻ vượt quá max_tokens_per_chunk
        if article_tokens > max_tokens_per_chunk:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            chunks.append([article])
            continue

        # Nếu thêm bài này vào mà VƯỢT QUÁ ngưỡng token HOẶC đạt giới hạn max_items_per_chunk
        if (current_tokens + article_tokens > max_tokens_per_chunk) or (len(current_chunk) >= max_items_per_chunk):
            chunks.append(current_chunk)
            current_chunk = [article]
            current_tokens = article_tokens
        else:
            current_chunk.append(article)
            current_tokens += article_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
