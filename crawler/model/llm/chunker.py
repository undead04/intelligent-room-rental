from typing import Dict, List

try:
    from crawler.utils.count_token import get_token_count
except ImportError:
    from utils.count_token import get_token_count


def create_dynamic_chunks(
    articles: List[Dict[str, str]],
    max_tokens_per_chunk: int = 2500,  # Ngưỡng an toàn tối ưu cho Task Extractor
    model_name: str = "gpt-4o",
) -> List[List[Dict[str, str]]]:
    """
    Gom các bài đăng vào chunk sao cho tổng token không vượt quá max_tokens_per_chunk.
    """
    chunks: List[List[Dict[str, str]]] = []
    current_chunk: List[Dict[str, str]] = []
    current_tokens = 0

    for article in articles:
        art_id = str(article.get("listing_id") or article.get("id", ""))
        article_text = f"ID: {art_id}\nText: {article.get('text', '')}"
        article_tokens = get_token_count(article_text, model_name)

        # EDGE CASE: Nếu 1 bài đơn lẻ vượt quá max_tokens_per_chunk
        if article_tokens > max_tokens_per_chunk:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            chunks.append([article])
            continue

        # Nếu thêm bài này vào mà VƯỢT QUÁ ngưỡng -> Đóng chunk cũ, mở chunk mới
        if current_tokens + article_tokens > max_tokens_per_chunk:
            chunks.append(current_chunk)
            current_chunk = [article]
            current_tokens = article_tokens
        else:
            current_chunk.append(article)
            current_tokens += article_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
