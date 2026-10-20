from typing import Any, Dict, List

from crawler.config.settings import (
    DEFAULT_MAX_ITEMS_PER_CHUNK,
    DEFAULT_MAX_TOKENS_PER_CHUNK,
)
from crawler.schema.listing import extract_listing_full_text
from crawler.utils.count_token import get_token_count


def create_dynamic_chunks(
    articles: List[Dict[str, Any]],
    max_tokens_per_chunk: int = DEFAULT_MAX_TOKENS_PER_CHUNK,
    max_items_per_chunk: int = DEFAULT_MAX_ITEMS_PER_CHUNK,
    model_name: str = "gpt-4o",
) -> List[List[Dict[str, Any]]]:
    """
    Gom các bài đăng vào chunk sao cho tổng token không vượt quá max_tokens_per_chunk
    và số bài trong chunk không vượt quá max_items_per_chunk (tránh tràn output tokens của LLM).
    """
    chunks: List[List[Dict[str, Any]]] = []
    current_chunk: List[Dict[str, Any]] = []
    current_tokens = 0

    for article in articles:
        art_id = str(article.get("listing_id") or article.get("id", ""))
        content = extract_listing_full_text(article)
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
