from typing import Dict, List

try:
    from crawler.utils.count_token import get_token_count
except ImportError:
    from utils.count_token import get_token_count


def create_dynamic_chunks(
    articles: List[Dict[str, str]],
    max_tokens_per_chunk: int = 2500,  # Ngưỡng an toàn tối ưu cho Task Extractor
    max_items_per_chunk: int = 15,     # Giới hạn tối đa 15 bài/chunk để output JSON không vượt quá trần 8192 tokens của Gemini
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
